import requests
import json
import os
import time

from tools.file_tool import read_file, write_file
from tools.code_runner import run_python_file
from tools.git_tool import git_commit_push
from tools.system_tool import run_safe_command, install_package, list_workspace
from tools.web_tool import create_web_project
from config import OLLAMA_URL, MODEL, OLLAMA_OPTIONS, WORKSPACE_DIR, MAX_RETRIES

SYSTEM_PROMPT = """You are an elite local AI coding agent running on Intel Core i5 10th Gen with 12GB RAM and NVIDIA MX 330 GPU.

You CAN:
1. Create complete multi-file Python/JavaScript/HTML projects
2. Install Python packages via pip
3. Run system commands (safe ones only)
4. Create web applications (Flask, FastAPI, HTML/CSS/JS)
5. Push projects to GitHub automatically
6. Debug and fix code automatically (up to 4 retries)
7. Create README, requirements.txt, .gitignore automatically

AVAILABLE ACTIONS (return ONE JSON per response):

{"action": "write_file", "args": {"path": "app.py", "content": "..."}}
{"action": "read_file", "args": {"path": "app.py"}}
{"action": "run_python_file", "args": {"path": "app.py"}}
{"action": "run_command", "args": {"cmd": "pip install flask", "safe": true}}
{"action": "install_package", "args": {"package": "flask"}}
{"action": "create_web_project", "args": {"name": "myapp", "type": "flask"}}
{"action": "git_commit_push", "args": {"path": "./workspace/myapp", "message": "V1 initial"}}
{"action": "list_workspace", "args": {}}
{"action": "none", "message": "Task complete"}

RULES:
- NEVER use input() or infinite loops
- Programs must run and exit automatically
- Always create requirements.txt and README.md
- Fix errors automatically (max 4 retries)
- After project creation, ALWAYS git_commit_push
- Use semantic versioning: "V1 init", "V2 feature", etc.
- For web projects, always include working demo data
- Optimize code for i5-10th / 12GB RAM (no heavy ML models)
- Do NOT use PyTorch, TensorFlow, or other heavy ML libraries
"""

MEMORY_FILE = os.path.join(WORKSPACE_DIR, ".agent_memory.json")
SESSIONS_FILE = os.path.join(WORKSPACE_DIR, ".sessions.json")

# In-memory sessions store: { session_id: { id, name, messages[], created_at } }
_sessions: dict = {}


# ──────────────────────────── sessions ───────────────────────────────────────

def _load_sessions_from_disk():
    global _sessions
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                _sessions = json.load(f)
        except Exception:
            _sessions = {}


def _save_sessions_to_disk():
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(_sessions, f, ensure_ascii=False, indent=2)


_load_sessions_from_disk()


def create_session(name: str = None) -> dict:
    sid = str(int(time.time() * 1000))
    session = {
        "id": sid,
        "name": name or f"Session {len(_sessions) + 1}",
        "messages": [],
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _sessions[sid] = session
    _save_sessions_to_disk()
    return session


def get_session(sid: str) -> dict | None:
    return _sessions.get(sid)


def list_sessions() -> list:
    return sorted(_sessions.values(), key=lambda s: s["created_at"], reverse=True)


def delete_session(sid: str):
    _sessions.pop(sid, None)
    _save_sessions_to_disk()


def _append_message(sid: str, role: str, content: str):
    if sid and sid in _sessions:
        _sessions[sid]["messages"].append({
            "role": role,
            "content": content,
            "time": time.strftime("%H:%M:%S"),
        })
        _save_sessions_to_disk()


def _session_context(sid: str) -> str:
    if not sid or sid not in _sessions:
        return ""
    msgs = _sessions[sid]["messages"][-8:]  # last 8 messages
    ctx = ""
    for m in msgs:
        ctx += f"\n{m['role'].upper()}: {m['content'][:400]}\n"
    return ctx


# ──────────────────────────── memory ─────────────────────────────────────────

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"projects": []}
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_memory(data):
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def remember_project(user_input, files, run_file, result):
    memory = load_memory()
    memory["projects"].append({
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "task": user_input,
        "files": files,
        "run_file": run_file,
        "success": result.get("returncode") == 0,
        "stdout": result.get("stdout", "")[:500],
        "stderr": result.get("stderr", "")[:200],
    })
    save_memory(memory)


# ──────────────────────────── LLM helpers ────────────────────────────────────

def _parse_ollama(response) -> str:
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"Ollama: {data['error']}")
    if "response" not in data:
        raise RuntimeError(f"Ollama unexpected response: {list(data.keys())}")
    return data["response"]


def ask_llm(prompt: str) -> str:
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": OLLAMA_OPTIONS,
            "keep_alive": "30m",
        }, timeout=180)
        response.raise_for_status()
        return _parse_ollama(response)
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Ollama serverga ulanib bo'lmadi ({OLLAMA_URL}).\n"
            f"Iltimos: `ollama serve` yoki `ollama run {MODEL}` buyrug'ini bajaring."
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama javob bermadi (180s). Model yuklanayotgan bo'lishi mumkin.")


def ask_llm_json(prompt: str) -> dict:
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": OLLAMA_OPTIONS,
            "keep_alive": "30m",
        }, timeout=180)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Ollama serverga ulanib bo'lmadi ({OLLAMA_URL}).\n"
            f"Iltimos: `ollama serve` yoki `ollama run {MODEL}` buyrug'ini bajaring."
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama javob bermadi (180s). Model yuklanayotgan bo'lishi mumkin.")
    raw = _parse_ollama(response).strip()
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


def fix_code(code: str, error: str) -> str:
    prompt = f"""Fix this Python code. Return ONLY corrected code. No explanation.

Code:
{code}

Error:
{error}

CRITICAL:
- Do NOT use input() or infinite loops
- Script must run demo actions automatically and exit
"""
    return extract_code(ask_llm(prompt))


def generate_project_manifest(user_input: str, session_context: str = "") -> dict:
    ctx_block = f"\nConversation context:\n{session_context}\n" if session_context else ""
    prompt = f"""Return ONLY valid JSON. No explanation.
{ctx_block}
Create a complete GitHub-ready Python project for this task:
"{user_input}"

Hardware: Intel Core i5 10th Gen, 12GB RAM, NVIDIA MX 330 2GB
Do NOT use PyTorch, TensorFlow, or other heavy ML libraries.

JSON format:
{{
  "project_name": "short-name-no-spaces",
  "files": [
    {{"path": "main.py", "content": "..."}},
    {{"path": "README.md", "content": "# Project\\n..."}},
    {{"path": "requirements.txt", "content": "flask>=3.0.0\\n"}},
    {{"path": ".gitignore", "content": "__pycache__/\\n*.pyc\\n.env\\n"}}
  ],
  "run": "main.py"
}}

Rules:
- project_name must be lowercase with hyphens (e.g. "todo-app")
- main.py must run automatically and print demo output
- Do NOT use input() or infinite loops
- For web apps: use Flask on port 5001 (agent UI is on 5000)
- Always include README.md and requirements.txt
"""
    return ask_llm_json(prompt)


# ──────────────────────────── chat (non-code) ─────────────────────────────────

def chat_reply(user_input: str, session_context: str = "") -> str:
    ctx_block = f"\nConversation context:\n{session_context}\n" if session_context else ""
    prompt = f"""You are a helpful AI assistant.{ctx_block}

User: {user_input}
Assistant:"""
    return ask_llm(prompt).strip()


# ──────────────────────────── main agent ─────────────────────────────────────

def run_agent(user_input: str, log_callback=None, session_id: str = None) -> dict:
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    _append_message(session_id, "user", user_input)
    ctx = _session_context(session_id)

    log("Manifest tayyorlanmoqda...")
    try:
        manifest = generate_project_manifest(user_input, ctx)
    except Exception as e:
        err = f"LLM xatosi: {e}"
        log(err)
        _append_message(session_id, "assistant", err)
        return {"status": "failed", "error": err}

    files = manifest.get("files", [])
    run_file = manifest.get("run", "main.py")
    project_name = manifest.get("project_name", "project")

    project_dir = os.path.join(WORKSPACE_DIR, project_name)
    os.makedirs(project_dir, exist_ok=True)

    created = []
    for f in files:
        path = f.get("path")
        content = f.get("content", "")
        if not path:
            continue
        full_path = os.path.join(project_dir, path)
        dir_part = os.path.dirname(full_path)
        if dir_part:
            os.makedirs(dir_part, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        created.append(path)
        log(f"Yaratildi: {path}")

    run_path = os.path.join(project_dir, run_file)
    log(f"Ishga tushirilmoqda: {run_file}")
    result = run_python_file(run_path)

    for attempt in range(MAX_RETRIES):
        if result.get("returncode") == 0:
            out_preview = result.get("stdout", "")[:200]
            log(f"Muvaffaqiyat! {out_preview}")
            git_result = git_commit_push(
                project_dir,
                f"V{attempt + 1} {project_name}: {user_input[:50]}",
            )
            log(f"Git: {git_result['stdout'][:120]}")
            remember_project(user_input, created, run_file, result)
            summary = f"Loyiha yaratildi: {project_name}. Fayllar: {', '.join(created)}"
            _append_message(session_id, "assistant", summary)
            return {
                "status": "success",
                "project_name": project_name,
                "created_files": created,
                "run_file": run_file,
                "result": result,
                "git": git_result,
            }

        log(f"Xato (urinish {attempt + 1}/{MAX_RETRIES}) — tuzatilmoqda...")
        broken_code = open(run_path, "r", encoding="utf-8").read() if os.path.exists(run_path) else ""
        try:
            fixed_code = fix_code(broken_code, result.get("stderr", ""))
        except Exception as e:
            log(f"Fix xatosi: {e}")
            break
        with open(run_path, "w", encoding="utf-8") as fh:
            fh.write(fixed_code)
        result = run_python_file(run_path)

    remember_project(user_input, created, run_file, result)
    stderr = result.get("stderr", "").strip()
    stdout = result.get("stdout", "").strip()
    detail = stderr or stdout or "Noma'lum xato"
    err_msg = f"Loyiha ishlamadi ({project_name}).\n\nXato:\n```\n{detail[:400]}\n```"
    _append_message(session_id, "assistant", err_msg)
    return {
        "status": "failed",
        "project_name": project_name,
        "created_files": created,
        "run_file": run_file,
        "result": result,
    }
