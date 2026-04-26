import requests
import json
from config import OLLAMA_URL, MODEL
from tools.file_tool import read_file, write_file
from tools.terminal_tool import suggest_command

SYSTEM_PROMPT = """
You are a local AI agent.

You MUST respond in JSON format.

Available tools:
1. write_file(path, content)
2. read_file(path)
3. suggest_command(cmd)

Format:

{
  "action": "write_file",
  "args": {
    "path": "file.py",
    "content": "print('hello')"
  }
}

OR

{
  "action": "suggest_command",
  "args": {
    "cmd": "winget install Telegram.TelegramDesktop"
  }
}

If no action needed:

{
  "action": "none",
  "message": "your answer"
}
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
            args = data["args"]
            result = write_file(args["path"], args["content"])

        elif action == "read_file":
            args = data["args"]
            result = read_file(args["path"])

        elif action == "suggest_command":
            args = data["args"]
            result = suggest_command(args["cmd"])

        elif action == "none":
            return {"final": data.get("message")}

        else:
            return {"error": "Unknown action"}

        # agentga natijani qaytaramiz
        history += f"\nAssistant: {raw}\nTool result: {result}"

    return {"final": "Max steps reached"}