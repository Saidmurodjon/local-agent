import subprocess

def suggest_command(cmd: str):
    return f"Run this command:\n{cmd}\n\nConfirm to execute."

def run_command(cmd: str):
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except Exception as e:
        return {"error": str(e)}