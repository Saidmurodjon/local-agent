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
        "stream": False,
        "format": "json"
    })
    return response.json()["response"]

def clean_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "").replace("```", "").strip()
    return raw

def run_agent(user_input):
    if "yarat" in user_input:
        code = """def buggy_function(x):
    return str(x) + 1

print(buggy_function(5))
"""
        write_file("bug_test.py", code)

    result = run_python_file("bug_test.py")

    if result.get("returncode") != 0:
        fixed_code = """def buggy_function(x):
    return x + 1

print(buggy_function(5))
"""
        write_file("bug_test.py", fixed_code)
        result = run_python_file("bug_test.py")

    return {
        "final": result
    }