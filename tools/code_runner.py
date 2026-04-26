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
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": f"File not found in workspace: {path}"
        }

    try:
        result = subprocess.run(
            ["python", full_path],
            capture_output=True,
            text=True,
            timeout=5
        )

        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }

    except subprocess.TimeoutExpired:
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": "Execution timeout: possible infinite loop or input() usage"
        }