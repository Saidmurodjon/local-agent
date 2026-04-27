import os
import subprocess
import sys

WORKSPACE = os.path.abspath("./workspace")


def run_python_file(path: str) -> dict:
    if not str(path).endswith(".py"):
        return {"returncode": 1, "stdout": "", "stderr": "Only .py files allowed"}

    # Accept both absolute paths and relative paths (relative to cwd or workspace)
    full_path = os.path.abspath(path)

    # Security: must be inside workspace
    if not full_path.startswith(WORKSPACE):
        return {"returncode": 1, "stdout": "", "stderr": "Access denied: path outside workspace"}

    if not os.path.exists(full_path):
        return {"returncode": 1, "stdout": "", "stderr": f"File not found: {full_path}"}

    try:
        result = subprocess.run(
            [sys.executable, full_path],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.dirname(full_path),
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[:3000],
            "stderr": result.stderr[:1000],
        }
    except subprocess.TimeoutExpired:
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": "Timeout (30s): infinite loop yoki input() ishlatilgan bo'lishi mumkin",
        }
    except Exception as e:
        return {"returncode": 1, "stdout": "", "stderr": str(e)}
