import os
import threading
from flask import Flask, render_template, request, jsonify
from agent import run_agent
from tools.system_tool import list_workspace
from tools.git_tool import git_commit_push, load_git_config, save_git_config

app = Flask(__name__)
task_status = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/run", methods=["POST"])
def run_task():
    data = request.json or {}
    user_input = data.get("prompt", "").strip()
    if not user_input:
        return jsonify({"error": "Prompt bo'sh"}), 400

    task_id = str(len(task_status) + 1)
    task_status[task_id] = {"status": "running", "log": []}

    def background_run():
        def on_log(msg):
            task_status[task_id]["log"].append(msg)

        try:
            result = run_agent(user_input, log_callback=on_log)
            task_status[task_id]["status"] = "done"
            task_status[task_id]["result"] = result
        except Exception as e:
            task_status[task_id]["status"] = "error"
            task_status[task_id]["error"] = str(e)

    thread = threading.Thread(target=background_run, daemon=True)
    thread.start()
    return jsonify({"task_id": task_id})


@app.route("/api/status/<task_id>")
def get_status(task_id):
    status = task_status.get(task_id, {"status": "not_found"})
    # Drain log so client gets new lines each poll
    log = status.pop("log", []) if "log" in status else []
    status["log"] = []
    response = dict(status)
    response["log"] = log
    task_status[task_id] = status
    return jsonify(response)


@app.route("/api/workspace")
def get_workspace():
    result = list_workspace()
    files = [f for f in result["stdout"].split("\n") if f] if result["stdout"] else []
    return jsonify({"files": files})


@app.route("/api/git/push", methods=["POST"])
def push_to_github():
    data = request.json or {}
    path = data.get("path", "").strip()
    message = data.get("message", "Auto commit from Local Agent")
    remote = data.get("remote", None) or None
    if not path:
        return jsonify({"returncode": 1, "stdout": "", "stderr": "Path required"}), 400
    result = git_commit_push(path, message, remote)
    return jsonify(result)


@app.route("/api/git/config", methods=["GET", "POST"])
def git_config():
    if request.method == "GET":
        return jsonify(load_git_config())
    save_git_config(request.json or {})
    return jsonify({"status": "saved"})


if __name__ == "__main__":
    os.makedirs("./workspace", exist_ok=True)
    print("Local Agent V11 starting on http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
