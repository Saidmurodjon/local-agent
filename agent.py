import requests
import json
from config import OLLAMA_URL, MODEL
from tools.file_tool import read_file, write_file
from tools.terminal_tool import suggest_command

SYSTEM_PROMPT = """
You are a local Windows AI agent.

CRITICAL RULE:
You MUST return ONLY valid JSON.
Do NOT use markdown.
Do NOT explain outside JSON.
Do NOT wrap JSON in ```.

User is on Windows.

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

3. run_command
{
  "action": "run_command",
  "args": {
    "cmd": "winget install Telegram.TelegramDesktop"
  }
}

4. suggest_command
{
  "action": "suggest_command",
  "args": {
    "cmd": "winget install Telegram.TelegramDesktop"
  }
}

5. none
{
  "action": "none",
  "message": "finished"
}

For installing Telegram Desktop on Windows, use:
winget install Telegram.TelegramDesktop

Always include args for tool actions.
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

def run_agent(user_input):
    prompt = SYSTEM_PROMPT + "\nUser: " + user_input
    history = prompt

    for step in range(5):  # max 5 step
        raw = ask_llm(history)

        try:
            data = json.loads(clean_json(raw))
        except:
            return {"error": "Invalid JSON", "raw": raw}

        action = data.get("action")

        if action == "write_file":
            args = data.get("args", {})
            result = write_file(args["path"], args["content"])

        elif action == "read_file":
            args = data.get("args", {})
            result = read_file(args["path"])

        elif action == "suggest_command":
            args = data.get("args", {})
            result = suggest_command(args["cmd"])

        elif action == "none":
            return {"final": data.get("message")}
        elif action == "run_command":
            args = data.get("args", {})
            cmd = args["cmd"]

            # MUHIM: avtomatik emas
            return {
                "confirm": True,
                "command": cmd,
                "message": "Run this command?"
            }
        else:
            return {"error": "Unknown action"}
         

        # agentga natijani qaytaramiz
        history += f"\nAssistant: {raw}\nTool result: {result}"
    
    return {"final": "Max steps reached"}