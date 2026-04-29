"""
Local Agent V12 — core agent loop.
Uses SQLite (db.py) for all state; files go into the session's folder.
"""
import re
import requests
import json
import os
import time

import db
import config as _cfg
from tools.code_runner import run_python_file
from tools.git_tool    import git_commit_push
from tools.system_tool import run_safe_command, install_package, list_workspace
from tools.web_tool    import create_web_project
from tools.finetune_tool import collect_sample

# pip name differs from import name for some common packages
_PKG_MAP = {
    "bs4": "beautifulsoup4",
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "serial": "pyserial",
    "usb": "pyusb",
    "gi": "PyGObject",
    "wx": "wxPython",
}

OLLAMA_URL     = _cfg.OLLAMA_URL
OLLAMA_OPTIONS = _cfg.OLLAMA_OPTIONS
MAX_RETRIES    = _cfg.MAX_RETRIES


# ──────────────────────────── model (switchable) ──────────────────────────────

_model_override: str | None = None

def _model() -> str:
    return _model_override or _cfg.MODEL


# ──────────────────────────── LLM helpers ────────────────────────────────────

def _parse_ollama(response) -> str:
    try:
        data = response.json()
    except Exception:
        raise RuntimeError(f"Ollama JSON parse error. Status: {response.status_code}")
    if "error" in data:
        raise RuntimeError(f"Ollama: {data['error']}")
    if "response" not in data:
        raise RuntimeError(f"Ollama kutilmagan javob: {list(data.keys())}")
    return data["response"]


def _ollama_error(e: Exception) -> RuntimeError:
    model = _model()
    if isinstance(e, requests.exceptions.ConnectionError):
        return RuntimeError("Ollama serverga ulanib bo'lmadi.\nBuyruq: `ollama serve`")
    if isinstance(e, requests.exceptions.Timeout):
        return RuntimeError("Ollama 180s ichida javob bermadi.")
    if isinstance(e, requests.exceptions.HTTPError):
        if e.response is not None and e.response.status_code == 404:
            available = ", ".join(_cfg.list_ollama_models()) or "hech qanday model yo'q"
            return RuntimeError(
                f"Model topilmadi: `{model}`\n"
                f"Mavjud: {available}\n"
                f"Yuklash: `ollama pull {model}`"
            )
    return RuntimeError(str(e))


def ask_llm(prompt: str) -> str:
    try:
        r = requests.post(OLLAMA_URL, json={
            "model": _model(), "prompt": prompt, "stream": False,
            "options": OLLAMA_OPTIONS, "keep_alive": "30m",
        }, timeout=180)
        r.raise_for_status()
        return _parse_ollama(r)
    except (requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.HTTPError) as e:
        raise _ollama_error(e)


def ask_llm_json(prompt: str) -> dict:
    try:
        r = requests.post(OLLAMA_URL, json={
            "model": _model(), "prompt": prompt, "stream": False,
            "format": "json", "options": OLLAMA_OPTIONS, "keep_alive": "30m",
        }, timeout=180)
        r.raise_for_status()
    except (requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.HTTPError) as e:
        raise _ollama_error(e)
    raw = _parse_ollama(r).strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def extract_code(raw: str) -> str:
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("python"):
            raw = raw.replace("python", "", 1)
    lines = []
    for line in raw.splitlines():
        if line.strip().lower().startswith("it seems"):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def sanitize_code(code: str) -> str:
    """Comment out blocking server calls (app.run, uvicorn.run, serve_forever)."""
    lines = code.splitlines()
    out = []
    for line in lines:
        if re.search(r'\bapp\.run\s*\(', line) or \
           re.search(r'\buvicorn\.run\s*\(', line) or \
           re.search(r'serve_forever\s*\(\s*\)', line):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}# {line.strip()}  # test mode: server not started")
            out.append(f'{indent}print("Server OK — test mode, routes defined")')
        else:
            out.append(line)
    return "\n".join(out)


def _install_requirements(req_path: str, log_fn) -> None:
    """Install packages from requirements.txt."""
    if not os.path.exists(req_path):
        return
    pkgs = []
    with open(req_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                pkgs.append(line)
    if not pkgs:
        return
    log_fn(f"Paketlar o'rnatilmoqda: {', '.join(pkgs)}")
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install"] + pkgs + ["--quiet"],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode == 0:
        log_fn(f"O'rnatildi: {', '.join(pkgs)}")
    else:
        log_fn(f"pip xato: {result.stderr[:300]}")


def _missing_module(error_text: str) -> str | None:
    """Extract missing module name from ModuleNotFoundError."""
    m = re.search(r"No module named ['\"]([^'\"]+)['\"]", error_text)
    if m:
        name = m.group(1).split(".")[0]
        return _PKG_MAP.get(name, name)
    return None


def fix_code(code: str, error: str) -> str:
    prompt = f"""Fix this Python code. Return ONLY corrected code. No explanation.

Code:
{code}

Error:
{error}

CRITICAL:
- Do NOT use input() or infinite loops
- Do NOT call app.run() or uvicorn.run()
- Script must print demo output and exit automatically
"""
    return extract_code(ask_llm(prompt))


# ──────────────────────────── manifest ───────────────────────────────────────

def _summarize_context(ctx: str) -> str:
    """Compress long context to avoid overflow."""
    if not ctx or len(ctx) < 800:
        return ctx
    # Take only last 2 exchanges max (≤600 chars)
    lines = [l for l in ctx.strip().splitlines() if l.strip()]
    return "\n".join(lines[-10:])[:600]


def generate_project_manifest(user_input: str, session_context: str = "") -> dict:
    short_ctx = _summarize_context(session_context)
    ctx_block = f"\nPrevious context:\n{short_ctx}\n" if short_ctx else ""
    prompt = f"""Return ONLY valid JSON. No explanation.
{ctx_block}
Create a complete GitHub-ready Python project for:
"{user_input}"

Hardware: i5-10th Gen, 12GB RAM, NVIDIA MX230 2GB VRAM. No PyTorch/TensorFlow.

JSON:
{{
  "project_name": "short-name-with-hyphens",
  "files": [
    {{"path": "main.py", "content": "..."}},
    {{"path": "README.md", "content": "# ..."}},
    {{"path": "requirements.txt", "content": ""}},
    {{"path": ".gitignore", "content": "__pycache__/\\n*.pyc\\n"}}
  ],
  "run": "main.py"
}}

Rules:
- project_name: lowercase hyphens only
- main.py: print demo output, then EXIT automatically
- NEVER call app.run() or uvicorn.run() in main.py
- For web apps: define routes but call app.test_client() for demo, not app.run()
- requirements.txt: all pip dependencies
- Keep main.py under 80 lines
"""
    return ask_llm_json(prompt)


# ──────────────────────────── chat reply ─────────────────────────────────────

def chat_reply(user_input: str, session_id: str = None, model_override: str = None) -> str:
    global _model_override
    _model_override = model_override
    ctx = db.msg_context(session_id) if session_id else ""
    ctx_block = f"\nConversation history:\n{ctx}\n" if ctx else ""
    prompt = f"""You are a helpful AI assistant.{ctx_block}
User: {user_input}
Assistant:"""
    result = ask_llm(prompt).strip()
    _model_override = None
    return result


# ──────────────────────────── main agent ─────────────────────────────────────

def run_agent(user_input: str, log_callback=None, session_id: str = None, model_override: str = None) -> dict:
    global _model_override
    _model_override = model_override
    def log(msg, msg_type: str = "log"):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
        if session_id:
            db.msg_add(session_id, "assistant", msg, msg_type)

    # Save user message
    if session_id:
        db.msg_add(session_id, "user", user_input, "chat")

    ctx = db.msg_context(session_id) if session_id else ""

    # Resolve session folder
    sess = db.session_get(session_id) if session_id else None
    session_folder = sess["folder"] if sess and sess.get("folder") else os.path.abspath("./workspace")

    log("Manifest tayyorlanmoqda...")
    try:
        manifest = generate_project_manifest(user_input, ctx)
    except Exception as e:
        err = f"LLM xatosi: {e}"
        log(err, "error")
        return {"status": "failed", "error": err}

    files        = manifest.get("files", [])
    run_file     = manifest.get("run", "main.py")
    project_name = manifest.get("project_name", "project")

    # Project folder lives inside the session folder
    project_dir = os.path.join(session_folder, project_name)
    os.makedirs(project_dir, exist_ok=True)

    created = []
    for f in files:
        path    = f.get("path")
        content = f.get("content", "")
        if not path:
            continue
        full_path = os.path.join(project_dir, path)
        dir_part  = os.path.dirname(full_path)
        if dir_part:
            os.makedirs(dir_part, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        created.append(path)
        log(f"Yaratildi: {path}")

    # Sanitize before first run
    run_path = os.path.join(project_dir, run_file)
    if os.path.exists(run_path):
        raw   = open(run_path, encoding="utf-8").read()
        clean = sanitize_code(raw)
        if clean != raw:
            open(run_path, "w", encoding="utf-8").write(clean)
            log("Server chaqiruvlari test uchun o'chirildi")

    # Auto-install requirements before first run
    req_path = os.path.join(project_dir, "requirements.txt")
    _install_requirements(req_path, log)

    log(f"Ishga tushirilmoqda: {run_file}")
    result = run_python_file(run_path)

    for attempt in range(MAX_RETRIES):
        if result.get("returncode") == 0:
            out_preview = result.get("stdout", "")[:200]
            log(f"Muvaffaqiyat! {out_preview}")

            # Git commit
            git_result = git_commit_push(
                project_dir,
                f"V{attempt + 1} {project_name}: {user_input[:50]}",
            )
            log(f"Git: {git_result['stdout'][:120]}")

            # Save project record
            if session_id:
                db.project_save(
                    session_id, project_name, project_dir, created,
                    "success", result.get("stdout", ""), result.get("stderr", ""),
                )

            # Auto-collect fine-tune sample
            try:
                main_code = open(run_path, encoding="utf-8").read()
                collect_sample(
                    prompt=user_input,
                    completion=main_code,
                    quality=4,
                    category="code",
                )
                log("Fine-tune sample saqlandi")
            except Exception:
                pass

            # Summarise in chat
            summary = (
                f"**Muvaffaqiyat!** `{project_name}` loyihasi yaratildi.\n"
                f"Fayllar: {', '.join(f'`{f}`' for f in created)}\n"
                f"```\n{out_preview}\n```"
            )
            if session_id:
                db.msg_add(session_id, "assistant", summary, "chat")

            _model_override = None
            return {
                "status": "success",
                "project_name": project_name,
                "project_dir": project_dir,
                "created_files": created,
                "run_file": run_file,
                "result": result,
                "git": git_result,
            }

        log(f"Xato (urinish {attempt + 1}/{MAX_RETRIES}) — tuzatilmoqda...")
        broken_code = open(run_path, encoding="utf-8").read() if os.path.exists(run_path) else ""
        error_text  = result.get("stderr", "") or result.get("stdout", "")

        # Auto-install missing module then retry without modifying code
        missing = _missing_module(error_text)
        if missing:
            log(f"Modul topilmadi: {missing} — o'rnatilmoqda...")
            install_package(missing)
            result = run_python_file(run_path)
            continue

        try:
            fixed = sanitize_code(fix_code(broken_code, error_text))
        except Exception as e:
            log(f"Fix xatosi: {e}")
            break
        with open(run_path, "w", encoding="utf-8") as fh:
            fh.write(fixed)
        result = run_python_file(run_path)

    # Save failed project
    if session_id:
        db.project_save(
            session_id, project_name, project_dir, created,
            "failed", result.get("stdout", ""), result.get("stderr", ""),
        )

    stderr  = result.get("stderr", "").strip()
    stdout  = result.get("stdout", "").strip()
    detail  = stderr or stdout or "Noma'lum xato"
    err_msg = f"Loyiha ishlamadi (`{project_name}`).\n\n```\n{detail[:400]}\n```"
    if session_id:
        db.msg_add(session_id, "assistant", err_msg, "chat")

    _model_override = None
    return {
        "status": "failed",
        "project_name": project_name,
        "project_dir": project_dir,
        "created_files": created,
        "run_file": run_file,
        "result": result,
    }
