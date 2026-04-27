import requests
import json
from config import OLLAMA_URL, MODEL
from tools.file_tool import read_file, write_file
from tools.code_runner import run_python_file
from config import OLLAMA_URL, MODEL, OLLAMA_OPTIONS
import os
import time
from tools.git_tool import run_git
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


MEMORY_FILE = "./workspace/.agent_memory.json"

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"projects": []}

    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_memory(data):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def remember_project(user_input, files, run_file, result):
    memory = load_memory()
    memory["projects"].append({
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "task": user_input,
        "files": files,
        "run_file": run_file,
        "success": result.get("returncode") == 0,
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", "")
    })
    save_memory(memory)

def ask_llm(prompt):
    response = requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": OLLAMA_OPTIONS,
        "keep_alive": "30m"
    }, timeout=180)

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
CRITICAL:
- Do NOT create menu-based apps.
- Do NOT use input().
- Do NOT wait for user interaction.
- The script must run demo actions automatically and exit.
- For CLI-style apps, simulate demo data inside main.py.

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
            setup_git_repo()
            remember_project(user_input, created, run_file, result)
            return {
                "status": "success",
                "created_files": created,
                "run_file": run_file,
                "git": "initialized",
                "result": result
            }

        broken_code = read_file(run_file)

        fixed_code = fix_code(
            broken_code,
            result.get("stderr", "")
        )

        write_file(run_file, fixed_code)
        result = run_python_file(run_file)
        remember_project(user_input, created, run_file, result)
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
        "format": "json",
        "options": OLLAMA_OPTIONS,
        "keep_alive": "30m"
    }, timeout=180)

    return json.loads(clean_json(response.json()["response"]))
def generate_project_manifest(user_input):
    prompt = f"""
Return ONLY valid JSON.

Create a GitHub-ready Python project.

JSON format:
{{
  "files": [
    {{
      "path": "main.py",
      "content": "print('demo')"
    }},
    {{
      "path": "README.md",
      "content": "# Project\\n\\nHow to run..."
    }},
    {{
      "path": "requirements.txt",
      "content": ""
    }},
    {{
      "path": ".gitignore",
      "content": "__pycache__/\\n*.pyc\\n.env\\n.venv/\\n"
    }}
  ],
  "run": "main.py"
}}

Rules:
- Use only Python standard library unless necessary.
- Do NOT use input().
- Do NOT use infinite loops.
- Program must run and exit automatically.
- Program must print demo output.
- Include README with usage instructions.
- Include requirements.txt.
- Include .gitignore.
- Keep project simple and runnable.

Task:
{user_input}
"""
    return ask_llm_json(prompt)
def setup_git_repo():
    run_git("git init")
    run_git("git add .")
    run_git('git commit -m "Initial commit: generated by AI agent"')