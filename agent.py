import requests
import json
import os
import time

from tools.file_tool import read_file, write_file
from tools.code_runner import run_python_file
from tools.git_tool import git_commit_push
from tools.system_tool import run_safe_command, install_package, list_workspace
from tools.web_tool import create_web_project
from config import OLLAMA_URL, MODEL, OLLAMA_OPTIONS, WORKSPACE_DIR, MAX_RETRIES

SYSTEM_PROMPT = """You are an elite local AI coding agent running on Intel Core i5 10th Gen with 12GB RAM and NVIDIA MX 330 GPU.

You CAN:
1. Create complete multi-file Python/JavaScript/HTML projects
2. Install Python packages via pip
3. Run system commands (safe ones only)
4. Create web applications (Flask, FastAPI, HTML/CSS/JS)
5. Push projects to GitHub automatically
6. Debug and fix code automatically (up to 4 retries)
7. Create README, requirements.txt, .gitignore automatically

AVAILABLE ACTIONS (return ONE JSON per response):

{"action": "write_file", "args": {"path": "app.py", "content": "..."}}
{"action": "read_file", "args": {"path": "app.py"}}
{"action": "run_python_file", "args": {"path": "app.py"}}
{"action": "run_command", "args": {"cmd": "pip install flask", "safe": true}}
{"action": "install_package", "args": {"package": "flask"}}
{"action": "create_web_project", "args": {"name": "myapp", "type": "flask"}}
{"action": "git_commit_push", "args": {"path": "./workspace/myapp", "message": "V1 initial"}}
{"action": "list_workspace", "args": {}}
{"action": "none", "message": "Task complete"}

RULES:
- NEVER use input() or infinite loops
- Programs must run and exit automatically
- Always create requirements.txt and README.md
- Fix errors automatically (max 4 retries)
- After project creation, ALWAYS git_commit_push
- Use semantic versioning: "V1 init", "V2 feature", etc.
- For web projects, always include working demo data
- Optimize code for i5-10th / 12GB RAM (no heavy ML models)
- Do NOT use PyTorch, TensorFlow, or other heavy ML libraries
"""

MEMORY_FILE = os.path.join(WORKSPACE_DIR, ".agent_memory.json")


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"projects": []}
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_memory(data):
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
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
        "stdout": result.get("stdout", "")[:500],
        "stderr": result.get("stderr", "")[:200],
    })
    save_memory(memory)


def ask_llm(prompt):
    response = requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": OLLAMA_OPTIONS,
        "keep_alive": "30m",
    }, timeout=180)
    return response.json()["response"]


def ask_llm_json(prompt):
    response = requests.post(OLLAMA_URL, json={
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": OLLAMA_OPTIONS,
        "keep_alive": "30m",
    }, timeout=180)
    raw = response.json()["response"].strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def extract_code(raw: str) -> str:
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("python"):
            raw = raw.replace("python", "", 1)
    lines = raw.splitlines()
    code_lines = []
    for line in lines:
        if line.strip().lower().startswith("it seems"):
            break
        code_lines.append(line)
    return "\n".join(code_lines).strip()


def fix_code(code, error):
    prompt = f"""Fix this Python code. Return ONLY corrected code. No explanation.

Code:
{code}

Error:
{error}

CRITICAL:
- Do NOT use input() or infinite loops
- Do NOT create menu-based apps
- Script must run demo actions automatically and exit
"""
    raw = ask_llm(prompt)
    return extract_code(raw)


def generate_project_manifest(user_input):
    prompt = f"""Return ONLY valid JSON. No explanation.

Create a complete GitHub-ready Python project for this task:
"{user_input}"

Hardware: Intel Core i5 10th Gen, 12GB RAM, NVIDIA MX 330 2GB
Do NOT use heavy ML models (no PyTorch, no TensorFlow).
Use only CPU-friendly libraries.

JSON format:
{{
  "project_name": "short-name-no-spaces",
  "files": [
    {{"path": "main.py", "content": "..."}},
    {{"path": "README.md", "content": "# Project\\n..."}},
    {{"path": "requirements.txt", "content": "flask>=3.0.0\\n"}},
    {{"path": ".gitignore", "content": "__pycache__/\\n*.pyc\\n.env\\n"}}
  ],
  "run": "main.py"
}}

Rules:
- project_name must be lowercase with hyphens (e.g. "todo-app", "web-scraper")
- main.py must run automatically and print demo output
- Do NOT use input() or infinite loops
- Include requirements.txt with ALL dependencies
- For web apps: use Flask on port 5001 (not 5000, that's the agent UI)
- Always add README.md with setup instructions
- Keep code clean and functional
"""
    return ask_llm_json(prompt)


def run_agent(user_input: str, log_callback=None) -> dict:
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    log("Manifest tayyorlanmoqda...")
    manifest = generate_project_manifest(user_input)

    files = manifest.get("files", [])
    run_file = manifest.get("run", "main.py")
    project_name = manifest.get("project_name", "project")

    project_dir = os.path.join(WORKSPACE_DIR, project_name)
    os.makedirs(project_dir, exist_ok=True)

    created = []
    for f in files:
        path = f.get("path")
        content = f.get("content", "")
        if not path:
            continue
        full_path = os.path.join(project_dir, path)
        dir_part = os.path.dirname(full_path)
        if dir_part:
            os.makedirs(dir_part, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        created.append(path)
        log(f"Yaratildi: {path}")

    run_path = os.path.join(project_dir, run_file)
    log(f"Ishga tushirilmoqda: {run_file}")
    result = run_python_file(run_path)

    for attempt in range(MAX_RETRIES):
        if result.get("returncode") == 0:
            log(f"Muvaffaqiyat! Output: {result.get('stdout', '')[:200]}")
            git_result = git_commit_push(
                project_dir,
                f"V{attempt + 1} {project_name}: {user_input[:50]}",
            )
            log(f"Git: {git_result['stdout'][:120]}")
            remember_project(user_input, created, run_file, result)
            return {
                "status": "success",
                "project_name": project_name,
                "created_files": created,
                "run_file": run_file,
                "result": result,
                "git": git_result,
            }

        log(f"Xato (attempt {attempt + 1}/{MAX_RETRIES}) — tuzatilmoqda...")
        broken_code = open(run_path, "r", encoding="utf-8").read() if os.path.exists(run_path) else ""
        fixed_code = fix_code(broken_code, result.get("stderr", ""))
        with open(run_path, "w", encoding="utf-8") as fh:
            fh.write(fixed_code)
        result = run_python_file(run_path)

    remember_project(user_input, created, run_file, result)
    return {
        "status": "failed",
        "project_name": project_name,
        "created_files": created,
        "run_file": run_file,
        "result": result,
    }
