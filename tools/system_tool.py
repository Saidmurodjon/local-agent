import subprocess
import sys
import os

SAFE_COMMANDS = [
    "pip install", "pip list", "pip show",
    "python --version", "node --version", "npm install",
    "git init", "git add", "git commit", "git push", "git status",
    "dir", "ls", "mkdir", "echo",
    "npm init", "npm start", "npm run build",
    "flask run", "uvicorn", "python -m http.server",
    "winget install", "winget search", "winget show", "winget list",
    "choco install", "scoop install",
]


def run_safe_command(cmd: str, safe: bool = True) -> dict:
    if safe:
        allowed = any(cmd.strip().startswith(c) for c in SAFE_COMMANDS)
        if not allowed:
            return {"returncode": 1, "stdout": "", "stderr": f"Command not in safe list: {cmd}"}
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=120, cwd="./workspace"
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[:3000],
            "stderr": result.stderr[:1000],
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Command timed out (120s)"}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


def install_package(package: str) -> dict:
    """Install Python package via pip."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", package, "--quiet"],
        capture_output=True, text=True, timeout=120
    )
    return {
        "returncode": result.returncode,
        "stdout": f"Installed: {package}" if result.returncode == 0 else result.stdout,
        "stderr": result.stderr[:500],
    }


def install_app_winget(app_id: str) -> dict:
    """Install a Windows application via winget."""
    cmd = (
        f'winget install --id "{app_id}" '
        f"--accept-source-agreements --accept-package-agreements --silent"
    )
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=300
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[:3000],
            "stderr": result.stderr[:1000],
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "Install timed out (5 min)"}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


def search_winget(query: str) -> dict:
    """Search winget for an app."""
    try:
        result = subprocess.run(
            f'winget search "{query}"',
            shell=True, capture_output=True, text=True, timeout=30
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:500],
        }
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


def list_workspace() -> dict:
    files = []
    workspace = "./workspace"
    if os.path.exists(workspace):
        for root, dirs, filenames in os.walk(workspace):
            dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", "node_modules", ".venv"]]
            for f in filenames:
                if f.startswith("."):
                    continue
                rel_path = os.path.relpath(os.path.join(root, f), workspace)
                files.append(rel_path)
    return {"returncode": 0, "stdout": "\n".join(files), "stderr": ""}
