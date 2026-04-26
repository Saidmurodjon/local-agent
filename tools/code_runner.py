import os
import subprocess

WORKSPACE = "./workspace"

def run_python_file(path: str):
    if not path.endswith(".py"):
        return {"error": "Only .py files allowed"}

    full_path = os.path.abspath(os.path.join(WORKSPACE, path))
    workspace_path = os.path.abspath(WORKSPACE)

    if not full_path.startswith(workspace_path):
        return {"error": "Access denied"}

    if not os.path.exists(full_path):
        return {"error": "File not found"}

    result = subprocess.run(
        ["python", full_path],
        capture_output=True,
        text=True,
        timeout=20
    )

    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr
    }