import requests
import json
from config import OLLAMA_URL, MODEL
from tools.file_tool import read_file, write_file
from tools.code_runner import run_python_file

SYSTEM_PROMPT = """
You are a local Python coding agent.

CRITICAL:
- Do NOT use input()
- Do NOT use infinite loops
- Program must run and exit automatically
- No user interaction required

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
If code uses input() or infinite loop, remove them.
Program must run automatically and finish.

"""
    raw = ask_llm(prompt)
    return extract_code(raw)

def run_agent(user_input):
    manifest = generate_project_manifest(user_input)

    files = manifest.get("files", [])
    run_file = manifest.get("run", "main.py")

    created = []

    for f in files:
        path = f.get("path")
        content = f.get("content", "")
        if not path:
            continue
        write_file(path, content)
        created.append(path)

    result = run_python_file(run_file)

    for attempt in range(3):
        if result.get("returncode") == 0:
            return {
                "status": "success",
                "created_files": created,
                "run_file": run_file,
                "result": result
            }

        broken_code = read_file(run_file)

        fixed_code = fix_code(
            broken_code,
            result.get("stderr", "")
        )

        write_file(run_file, fixed_code)
        result = run_python_file(run_file)

    return {
        "status": "failed",
        "created_files": created,
        "run_file": run_file,
        "result": result
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
def ask_llm_json(prompt):
    response = requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    })
    return json.loads(clean_json(response.json()["response"]))
def generate_project_manifest(user_input):
    prompt = f"""
Return ONLY valid JSON.

Create a small Python project.

JSON format:
{{
  "files": [
    {{
      "path": "main.py",
      "content": "print('hello')"
    }}
  ],
  "run": "main.py"
}}

Rules:
- Use only Python standard library.
- Do not use external packages.
- Include all required files.
- Keep it simple and runnable.
Program must print a demo output when run.
Do not leave stdout empty.
Include sample data and show result.

Task:
{user_input}
"""
    return ask_llm_json(prompt)