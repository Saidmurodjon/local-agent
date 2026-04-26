import subprocess

def suggest_command(cmd: str):
    return f"Run this command:\n{cmd}\n\nConfirm to execute."


def run_command(cmd: str):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.stdout + result.stderr
    except Exception as e:
        return str(e)