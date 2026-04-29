"""Local Agent V12 — Flask API server."""
import os
import json
import threading

import config as _cfg
import db
from flask import Flask, render_template, request, jsonify
from agent import run_agent, chat_reply
from tools.system_tool   import list_workspace, install_app_winget, search_winget
from tools.git_tool      import git_commit_push, load_git_config, save_git_config
from tools.finetune_tool import (
    collect_sample, export_jsonl, create_ollama_specialist,
    list_custom_models,
)

app = Flask(__name__)
task_status: dict = {}

REPOS_FILE = "./workspace/.repos.json"


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_repos() -> list:
    if os.path.exists(REPOS_FILE):
        try:
            with open(REPOS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_repos(repos: list):
    os.makedirs("./workspace", exist_ok=True)
    with open(REPOS_FILE, "w", encoding="utf-8") as f:
        json.dump(repos, f, ensure_ascii=False, indent=2)


# ── pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── sessions ──────────────────────────────────────────────────────────────────

@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    return jsonify(db.session_list())


@app.route("/api/sessions", methods=["POST"])
def new_session():
    data   = request.json or {}
    name   = data.get("name", "").strip() or f"Session {len(db.session_list())+1}"
    folder = data.get("folder", "").strip() or None
    model  = data.get("model", "").strip() or None
    sess   = db.session_create(name, folder, model)
    return jsonify(sess)


@app.route("/api/sessions/<sid>", methods=["GET"])
def get_session(sid):
    sess = db.session_get(sid)
    if not sess:
        return jsonify({"error": "not found"}), 404
    msgs = db.msg_list(sid)
    return jsonify({**sess, "messages": msgs})


@app.route("/api/sessions/<sid>", methods=["PATCH"])
def update_session(sid):
    data = request.json or {}
    allowed = {k: v for k, v in data.items() if k in ("name", "folder", "model")}
    if "folder" in allowed and allowed["folder"]:
        os.makedirs(allowed["folder"], exist_ok=True)
    db.session_update(sid, **allowed)
    return jsonify(db.session_get(sid))


@app.route("/api/sessions/<sid>", methods=["DELETE"])
def del_session(sid):
    db.session_delete(sid)
    return jsonify({"status": "deleted"})


@app.route("/api/sessions/<sid>/files")
def session_files(sid):
    sess = db.session_get(sid)
    if not sess:
        return jsonify({"files": []})
    folder = sess.get("folder") or "./workspace"
    files  = []
    if os.path.exists(folder):
        for root, dirs, fnames in os.walk(folder):
            dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", "node_modules", ".venv"]]
            for fn in fnames:
                if fn.startswith("."):
                    continue
                rel = os.path.relpath(os.path.join(root, fn), folder)
                files.append(rel.replace("\\", "/"))
    return jsonify({"folder": folder, "files": files})


# ── run agent ─────────────────────────────────────────────────────────────────

@app.route("/api/run", methods=["POST"])
def run_task():
    data       = request.json or {}
    user_input = data.get("prompt", "").strip()
    session_id = data.get("session_id") or None
    if not user_input:
        return jsonify({"error": "Prompt bo'sh"}), 400

    task_id = f"t{len(task_status)+1}"
    task_status[task_id] = {"status": "running", "log": []}

    sess_model = None
    if session_id:
        s = db.session_get(session_id)
        if s and s.get("model"):
            sess_model = s["model"]

    def bg():
        def on_log(msg):
            task_status[task_id]["log"].append(msg)
        try:
            result = run_agent(user_input, log_callback=on_log, session_id=session_id, model_override=sess_model)
            task_status[task_id]["status"] = "done"
            task_status[task_id]["result"] = result
        except Exception as e:
            task_status[task_id]["status"] = "error"
            task_status[task_id]["error"]  = str(e)
            if session_id:
                db.msg_add(session_id, "assistant", f"Xato: {e}", "error")

    threading.Thread(target=bg, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/api/status/<task_id>")
def get_status(task_id):
    entry = task_status.get(task_id, {"status": "not_found"})
    log   = entry.pop("log", [])
    entry["log"] = []
    task_status[task_id] = entry
    resp = dict(entry)
    resp["log"] = log
    return jsonify(resp)


# ── chat ──────────────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat():
    data       = request.json or {}
    user_input = data.get("prompt", "").strip()
    session_id = data.get("session_id") or None
    if not user_input:
        return jsonify({"error": "Prompt bo'sh"}), 400
    if session_id:
        db.msg_add(session_id, "user", user_input, "chat")
    sess_model = None
    if session_id:
        s = db.session_get(session_id)
        if s and s.get("model"):
            sess_model = s["model"]
    try:
        reply = chat_reply(user_input, session_id, model_override=sess_model)
        if session_id:
            db.msg_add(session_id, "assistant", reply, "chat")
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/sessions/<sid>/messages")
def get_messages(sid):
    return jsonify(db.msg_list(sid))


# ── workspace ─────────────────────────────────────────────────────────────────

@app.route("/api/workspace")
def get_workspace():
    result = list_workspace()
    files  = [f for f in result["stdout"].split("\n") if f] if result["stdout"] else []
    return jsonify({"files": files})


# ── git ───────────────────────────────────────────────────────────────────────

@app.route("/api/git/push", methods=["POST"])
def push_git():
    data    = request.json or {}
    path    = data.get("path", "").strip()
    message = data.get("message", "Auto commit V12")
    remote  = data.get("remote") or None
    if not path:
        return jsonify({"returncode": 1, "stdout": "", "stderr": "path required"}), 400
    return jsonify(git_commit_push(path, message, remote))


@app.route("/api/git/config", methods=["GET", "POST"])
def git_config():
    if request.method == "GET":
        return jsonify(load_git_config())
    save_git_config(request.json or {})
    return jsonify({"status": "saved"})


# ── repos ─────────────────────────────────────────────────────────────────────

@app.route("/api/repos", methods=["GET"])
def get_repos():
    return jsonify(_load_repos())


@app.route("/api/repos", methods=["POST"])
def add_repo():
    data = request.json or {}
    name = data.get("name", "").strip()
    url  = data.get("url",  "").strip()
    if not name or not url:
        return jsonify({"error": "name and url required"}), 400
    repos = _load_repos()
    for r in repos:
        if r["name"] == name:
            r["url"] = url
            _save_repos(repos)
            return jsonify({"status": "updated"})
    repos.append({"name": name, "url": url, "local_path": f"./workspace/{name}"})
    _save_repos(repos)
    return jsonify({"status": "added"})


@app.route("/api/repos/<name>", methods=["DELETE"])
def del_repo(name):
    _save_repos([r for r in _load_repos() if r["name"] != name])
    return jsonify({"status": "deleted"})


@app.route("/api/repos/clone", methods=["POST"])
def clone_repo():
    data = request.json or {}
    url  = data.get("url",  "").strip()
    name = data.get("name", "").strip()
    if not url:
        return jsonify({"error": "url required"}), 400
    import subprocess
    dest   = f"./workspace/{name}" if name else "./workspace"
    result = subprocess.run(f'git clone "{url}" "{dest}"',
                            shell=True, capture_output=True, text=True, timeout=120)
    return jsonify({"returncode": result.returncode,
                    "stdout": result.stdout[:2000],
                    "stderr": result.stderr[:1000]})


# ── install ───────────────────────────────────────────────────────────────────

@app.route("/api/install/search", methods=["POST"])
def install_search():
    query = (request.json or {}).get("query", "").strip()
    if not query:
        return jsonify({"error": "query required"}), 400
    return jsonify(search_winget(query))


@app.route("/api/install/app", methods=["POST"])
def install_app():
    app_id = (request.json or {}).get("app_id", "").strip()
    if not app_id:
        return jsonify({"error": "app_id required"}), 400
    task_id = f"install-{app_id}"
    task_status[task_id] = {"status": "running", "log": []}

    def do_install():
        task_status[task_id]["log"].append(f"O'rnatilmoqda: {app_id}...")
        result = install_app_winget(app_id)
        task_status[task_id]["status"] = "done"
        task_status[task_id]["result"] = result

    threading.Thread(target=do_install, daemon=True).start()
    return jsonify({"task_id": task_id})


# ── filesystem browser ────────────────────────────────────────────────────────

@app.route("/api/fs/ls")
def fs_ls():
    """List directory contents for folder browser."""
    path = request.args.get("path", "").strip()
    if not path:
        # Return drive roots on Windows, / on Linux
        import string, platform
        roots = []
        if platform.system() == "Windows":
            for d in string.ascii_uppercase:
                dp = f"{d}:\\"
                if os.path.exists(dp):
                    roots.append({"name": dp, "path": dp, "type": "drive"})
        else:
            roots = [{"name": "/", "path": "/", "type": "dir"}]
        return jsonify({"path": "", "parent": None, "items": roots})

    try:
        path = os.path.abspath(path)
        parent = os.path.dirname(path) if path != os.path.splitdrive(path)[0] + "\\" else None
        _SKIP = {"$recycle.bin","system volume information","documents and settings",
                 "programdata","recovery","$windows.~bt","$windows.~ws","windows.old",
                 "boot","efi","perflogs","dumpstack.log.tmp"}
        items = []
        with os.scandir(path) as it:
            for e in sorted(it, key=lambda x: (not x.is_dir(), x.name.lower())):
                if e.name.startswith("."):
                    continue
                if e.name.lower() in _SKIP:
                    continue
                if e.is_dir():
                    try:
                        stat = e.stat()
                    except Exception:
                        continue
                    items.append({"name": e.name, "path": e.path.replace("\\", "/"), "type": "dir"})
        return jsonify({"path": path.replace("\\", "/"), "parent": parent.replace("\\", "/") if parent else None, "items": items})
    except PermissionError:
        return jsonify({"path": path, "parent": None, "items": [], "error": "Permission denied"})
    except Exception as e:
        return jsonify({"path": path, "parent": None, "items": [], "error": str(e)})


# ── ollama ────────────────────────────────────────────────────────────────────

@app.route("/api/ollama/status")
def ollama_status():
    import requests as _req
    try:
        r = _req.get(_cfg.OLLAMA_BASE + "/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])] if r.ok else []
        gpu = _cfg.get_gpu_info()
        # Measure tok/sec
        tok_sec = 0
        try:
            ps = _req.get(_cfg.OLLAMA_BASE + "/api/ps", timeout=3).json()
            # Use a quick generation to measure
            pass
        except Exception:
            pass
        return jsonify({
            "online": r.ok,
            "current_model": _cfg.MODEL,
            "models": models,
            "gpu": gpu,
        })
    except Exception as e:
        return jsonify({"online": False, "current_model": _cfg.MODEL, "models": [], "error": str(e)})


@app.route("/api/ollama/model", methods=["POST"])
def set_model():
    name = (request.json or {}).get("model", "").strip()
    if not name:
        return jsonify({"error": "model name required"}), 400
    _cfg.MODEL = name
    return jsonify({"status": "ok", "model": _cfg.MODEL})


@app.route("/api/ollama/enable_gpu", methods=["POST"])
def enable_gpu():
    """Restart Ollama service with CUDA environment variables."""
    import subprocess
    import platform
    try:
        if platform.system() == "Windows":
            # Stop Ollama service
            subprocess.run("taskkill /F /IM ollama.exe", shell=True,
                           capture_output=True, timeout=10)
            import time; time.sleep(2)
            # Restart with GPU env
            env = os.environ.copy()
            env["OLLAMA_NUM_GPU"] = "20"
            env["CUDA_VISIBLE_DEVICES"] = "0"
            subprocess.Popen(
                ["ollama", "serve"],
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(3)
            return jsonify({"status": "restarted", "message": "Ollama CUDA bilan qayta ishga tushirildi"})
        else:
            return jsonify({"status": "manual", "message": "Linux: OLLAMA_NUM_GPU=20 ollama serve"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ── fine-tune ─────────────────────────────────────────────────────────────────

@app.route("/api/finetune/samples", methods=["GET"])
def ft_samples():
    return jsonify(db.ft_list_samples())


@app.route("/api/finetune/samples", methods=["POST"])
def ft_add():
    data = request.json or {}
    sid = collect_sample(
        prompt     = data.get("prompt", ""),
        completion = data.get("completion", ""),
        quality    = int(data.get("quality", 3)),
        category   = data.get("category", "code"),
    )
    return jsonify({"id": sid})


@app.route("/api/finetune/samples/<int:sid>/rate", methods=["POST"])
def ft_rate(sid):
    q = int((request.json or {}).get("quality", 3))
    db.ft_rate_sample(sid, q)
    return jsonify({"status": "ok"})


@app.route("/api/finetune/samples/<int:sid>", methods=["DELETE"])
def ft_delete(sid):
    db.ft_delete_sample(sid)
    return jsonify({"status": "deleted"})


@app.route("/api/finetune/export", methods=["POST"])
def ft_export():
    data       = request.json or {}
    min_q      = int(data.get("min_quality", 3))
    output     = data.get("output_path") or None
    result     = export_jsonl(output, min_q)
    return jsonify(result)


@app.route("/api/finetune/create", methods=["POST"])
def ft_create():
    data   = request.json or {}
    name   = data.get("name",   "").strip()
    domain = data.get("domain", "Python coding").strip()
    extra  = data.get("extra",  "").strip()
    base   = data.get("base_model", _cfg.MODEL)
    min_q  = int(data.get("min_quality", 4))
    if not name:
        return jsonify({"error": "name required"}), 400

    task_id = f"ft-{name}"
    task_status[task_id] = {"status": "running", "log": [f"Specialist yaratilmoqda: {name}"]}

    def do_create():
        result = create_ollama_specialist(name, base, domain, extra, min_q)
        task_status[task_id]["status"] = "done"
        task_status[task_id]["result"] = result
        if result.get("ok"):
            task_status[task_id]["log"].append(f"Model tayyor: ollama run {name}")
        else:
            task_status[task_id]["log"].append(f"Xato: {result.get('error')}")

    threading.Thread(target=do_create, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/api/finetune/jobs", methods=["GET"])
def ft_jobs():
    return jsonify(db.ft_list_jobs())


@app.route("/api/finetune/custom_models", methods=["GET"])
def ft_custom_models():
    return jsonify(list_custom_models())


# ── projects ──────────────────────────────────────────────────────────────────

@app.route("/api/projects")
def get_projects():
    sid = request.args.get("session_id")
    with db._conn() as con:
        if sid:
            rows = con.execute(
                "SELECT * FROM projects WHERE session_id=? ORDER BY id DESC", (sid,)
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM projects ORDER BY id DESC LIMIT 50").fetchall()
    return jsonify([dict(r) for r in rows])


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs("./workspace", exist_ok=True)
    print(f"Local Agent V12  http://localhost:5000  model={_cfg.MODEL}")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
