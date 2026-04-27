import os
import json
import threading
from flask import Flask, render_template, request, jsonify

import config as _cfg
from agent import (
    run_agent, chat_reply,
    create_session, get_session, list_sessions, delete_session,
    _append_message,
)
from tools.system_tool import list_workspace, install_app_winget, search_winget
from tools.git_tool import git_commit_push, load_git_config, save_git_config

app = Flask(__name__)
task_status: dict = {}

REPOS_FILE = "./workspace/.repos.json"


# ──────────────── helpers ────────────────────────────────────────────────────

def _load_repos() -> list:
    if os.path.exists(REPOS_FILE):
        try:
            with open(REPOS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_repos(repos: list):
    os.makedirs("./workspace", exist_ok=True)
    with open(REPOS_FILE, "w", encoding="utf-8") as f:
        json.dump(repos, f, ensure_ascii=False, indent=2)


# ──────────────── pages ──────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ──────────────── sessions ───────────────────────────────────────────────────

@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    return jsonify(list_sessions())


@app.route("/api/sessions", methods=["POST"])
def new_session():
    name = (request.json or {}).get("name", "").strip() or None
    session = create_session(name)
    return jsonify(session)


@app.route("/api/sessions/<sid>", methods=["GET"])
def get_session_detail(sid):
    s = get_session(sid)
    if not s:
        return jsonify({"error": "not found"}), 404
    return jsonify(s)


@app.route("/api/sessions/<sid>", methods=["DELETE"])
def del_session(sid):
    delete_session(sid)
    return jsonify({"status": "deleted"})


# ──────────────── run task ───────────────────────────────────────────────────

@app.route("/api/run", methods=["POST"])
def run_task():
    data = request.json or {}
    user_input = data.get("prompt", "").strip()
    session_id = data.get("session_id") or None
    if not user_input:
        return jsonify({"error": "Prompt bo'sh"}), 400

    task_id = str(len(task_status) + 1)
    task_status[task_id] = {"status": "running", "log": []}

    def background_run():
        def on_log(msg):
            task_status[task_id]["log"].append(msg)

        try:
            result = run_agent(user_input, log_callback=on_log, session_id=session_id)
            task_status[task_id]["status"] = "done"
            task_status[task_id]["result"] = result
        except Exception as e:
            task_status[task_id]["status"] = "error"
            task_status[task_id]["error"] = str(e)
            if session_id:
                _append_message(session_id, "assistant", f"Xato: {e}")

    threading.Thread(target=background_run, daemon=True).start()
    return jsonify({"task_id": task_id})


@app.route("/api/status/<task_id>")
def get_status(task_id):
    entry = task_status.get(task_id, {"status": "not_found"})
    log = entry.pop("log", [])
    entry["log"] = []
    task_status[task_id] = entry
    resp = dict(entry)
    resp["log"] = log
    return jsonify(resp)


# ──────────────── chat (non-code) ────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    user_input = data.get("prompt", "").strip()
    session_id = data.get("session_id") or None
    if not user_input:
        return jsonify({"error": "Prompt bo'sh"}), 400
    try:
        from agent import _session_context
        ctx = _session_context(session_id)
        reply = chat_reply(user_input, ctx)
        _append_message(session_id, "user", user_input)
        _append_message(session_id, "assistant", reply)
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ──────────────── workspace ──────────────────────────────────────────────────

@app.route("/api/workspace")
def get_workspace():
    result = list_workspace()
    files = [f for f in result["stdout"].split("\n") if f] if result["stdout"] else []
    return jsonify({"files": files})


# ──────────────── git ────────────────────────────────────────────────────────

@app.route("/api/git/push", methods=["POST"])
def push_to_github():
    data = request.json or {}
    path = data.get("path", "").strip()
    message = data.get("message", "Auto commit from Local Agent")
    remote = data.get("remote") or None
    if not path:
        return jsonify({"returncode": 1, "stdout": "", "stderr": "Path required"}), 400
    return jsonify(git_commit_push(path, message, remote))


@app.route("/api/git/config", methods=["GET", "POST"])
def git_config():
    if request.method == "GET":
        return jsonify(load_git_config())
    save_git_config(request.json or {})
    return jsonify({"status": "saved"})


# ──────────────── repos ──────────────────────────────────────────────────────

@app.route("/api/repos", methods=["GET"])
def get_repos():
    return jsonify(_load_repos())


@app.route("/api/repos", methods=["POST"])
def add_repo():
    data = request.json or {}
    name = data.get("name", "").strip()
    url = data.get("url", "").strip()
    if not name or not url:
        return jsonify({"error": "name and url required"}), 400
    repos = _load_repos()
    # update if exists
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
    repos = [r for r in _load_repos() if r["name"] != name]
    _save_repos(repos)
    return jsonify({"status": "deleted"})


@app.route("/api/repos/clone", methods=["POST"])
def clone_repo():
    data = request.json or {}
    url = data.get("url", "").strip()
    name = data.get("name", "").strip()
    if not url:
        return jsonify({"error": "url required"}), 400
    import subprocess
    dest = f"./workspace/{name}" if name else "./workspace"
    result = subprocess.run(
        f'git clone "{url}" "{dest}"',
        shell=True, capture_output=True, text=True, timeout=120
    )
    return jsonify({
        "returncode": result.returncode,
        "stdout": result.stdout[:2000],
        "stderr": result.stderr[:1000],
    })


# ──────────────── install ────────────────────────────────────────────────────

@app.route("/api/install/search", methods=["POST"])
def install_search():
    query = (request.json or {}).get("query", "").strip()
    if not query:
        return jsonify({"error": "query required"}), 400
    return jsonify(search_winget(query))


@app.route("/api/install/app", methods=["POST"])
def install_app():
    data = request.json or {}
    app_id = data.get("app_id", "").strip()
    if not app_id:
        return jsonify({"error": "app_id required"}), 400

    task_id = f"install-{app_id}"
    task_status[task_id] = {"status": "running", "log": []}

    def do_install():
        task_status[task_id]["log"].append(f"O'rnatilmoqda: {app_id}...")
        result = install_app_winget(app_id)
        task_status[task_id]["status"] = "done"
        task_status[task_id]["result"] = result
        if result["returncode"] == 0:
            task_status[task_id]["log"].append(f"Muvaffaqiyat: {app_id} o'rnatildi")
        else:
            task_status[task_id]["log"].append(f"Xato: {result['stderr'][:200]}")

    threading.Thread(target=do_install, daemon=True).start()
    return jsonify({"task_id": task_id})


# ──────────────── ollama ─────────────────────────────────────────────────────

@app.route("/api/ollama/status")
def ollama_status():
    import requests as _req
    try:
        r = _req.get(_cfg.OLLAMA_BASE + "/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])] if r.ok else []
        return jsonify({
            "online": r.ok,
            "current_model": _cfg.MODEL,
            "models": models,
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


# ──────────────── main ───────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs("./workspace", exist_ok=True)
    print("Local Agent V11 starting on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
