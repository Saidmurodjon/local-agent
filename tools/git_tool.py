import subprocess
import os
import json
from datetime import datetime

GIT_CONFIG_FILE = "./workspace/.git_remotes.json"


def load_git_config() -> dict:
    if os.path.exists(GIT_CONFIG_FILE):
        with open(GIT_CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_git_config(config: dict):
    os.makedirs(os.path.dirname(GIT_CONFIG_FILE), exist_ok=True)
    with open(GIT_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def git_commit_push(path: str, message: str, remote: str = None) -> dict:
    if not os.path.exists(path):
        return {"returncode": 1, "stdout": "", "stderr": f"Path not found: {path}"}

    def run(cmd):
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=path)

    if not os.path.exists(os.path.join(path, ".git")):
        run("git init")
        run("git branch -M main")

    config = load_git_config()
    project_name = os.path.basename(os.path.abspath(path))

    if remote:
        config[project_name] = remote
        save_git_config(config)
    elif project_name in config:
        remote = config[project_name]

    gitignore = os.path.join(path, ".gitignore")
    if not os.path.exists(gitignore):
        with open(gitignore, "w") as f:
            f.write("__pycache__/\n*.pyc\n.env\n.venv/\nnode_modules/\n*.log\n")

    run("git add -A")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    commit_result = run(f'git commit -m "{message} [{timestamp}]"')

    if commit_result.returncode != 0 and "nothing to commit" not in commit_result.stdout:
        return {
            "returncode": commit_result.returncode,
            "stdout": commit_result.stdout,
            "stderr": commit_result.stderr,
        }

    if remote:
        remotes_out = run("git remote -v").stdout
        if "origin" not in remotes_out:
            run(f"git remote add origin {remote}")
        push_result = run("git push -u origin main")
        return {
            "returncode": push_result.returncode,
            "stdout": f"Committed: {message}\nPushed to: {remote}\n{push_result.stdout}",
            "stderr": push_result.stderr,
        }

    return {
        "returncode": 0,
        "stdout": f"Committed locally: {message}\n(No remote configured — add GitHub URL to push)",
        "stderr": "",
    }


def run_git(cmd, cwd="./workspace"):
    try:
        result = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
        return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
    except Exception as e:
        return {"error": str(e)}
