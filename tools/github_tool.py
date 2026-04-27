import subprocess

def run_gh(cmd, cwd="./workspace"):
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
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