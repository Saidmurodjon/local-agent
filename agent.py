import requests
import json
from config import OLLAMA_URL, MODEL
from tools.file_tool import write_file
from tools.code_runner import run_python_file

SYSTEM_PROMPT = """
You are a local Python coding agent.

CRITICAL RULE:
You MUST return ONLY valid JSON.
Do NOT use markdown.
Do NOT explain outside JSON.
Do NOT wrap JSON in ```.

Available actions:

1. write_file
{
  "action": "write_file",
  "args": {
    "path": "example.py",
    "content": "print('hello')"
  }
}

2. read_file
{
  "action": "read_file",
  "args": {
    "path": "example.py"
  }
}

3. run_python_file
{
  "action": "run_python_file",
  "args": {
    "path": "script.py"
  }
}

4. none
{
  "action": "none",
  "message": "finished"
}

Rules:
- Return exactly ONE JSON object per response.
- Never return multiple JSON objects.
- Never finish immediately.
- If user asks to create or edit a file, use write_file.
- If user asks to run Python code, use run_python_file.
- If Python execution returns stderr or non-zero returncode, fix the file using write_file, then run_python_file again.
- Do not use shell commands.
- Do not invent commands.
- Continue until task is fully done.
- Always include args for tool actions.
"""
def ask_llm(prompt):
    response = requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "prompt": prompt,
        "stream": False
    })
    return response.json()["response"]

def clean_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "").replace("```", "").strip()
    return raw

def generate_code(user_input):
    prompt = f"""
Return ONLY Python code.
No explanation.
No text.
No markdown.

Task:
{user_input}
"""
    raw = ask_llm(prompt)
    return extract_code(raw)


def fix_code(code, error):
    prompt = f"""
Fix this Python code.

Return ONLY corrected code.
No explanation.

Code:
{code}

Error:
{error}
"""
    raw = ask_llm(prompt)
    return extract_code(raw)


def run_agent(user_input):
    path = "dynamic_task.py"

    code = generate_code(user_input)
    write_file(path, code)

    result = run_python_file(path)

    for attempt in range(3):
        if result.get("returncode") == 0:
            return {
                "status": "success",
                "file": path,
                "result": result
            }

        error = result.get("stderr", "")
        code = fix_code(code, error)
        write_file(path, code)
        result = run_python_file(path)

    return {
        "status": "failed",
        "file": path,
        "last_result": result
    }
def extract_code(raw: str) -> str:
    # agar ```python block bo‘lsa
    if "```" in raw:
        raw = raw.split("```")[1]

        if raw.startswith("python"):
            raw = raw.replace("python", "", 1)

    # explanationlarni kesamiz
    lines = raw.splitlines()

    code_lines = []
    for line in lines:
        # explanation boshlansa to‘xtatamiz
        if line.strip().lower().startswith("it seems"):
            break
        if line.strip().startswith("#"):
            continue
        code_lines.append(line)

    return "\n".join(code_lines).strip()