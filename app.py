from fastapi import FastAPI
from pydantic import BaseModel
from agent import run_agent

app = FastAPI()

class Request(BaseModel):
    message: str

class ConfirmRequest(BaseModel):  
    cmd: str

@app.post("/chat")
def chat(req: Request):
    result = run_agent(req.message)
    return {
    "status": "done",
    "output": result["stdout"],
    "error": result["stderr"]
}

@app.post("/confirm")
def confirm(req: ConfirmRequest):
    from tools.terminal_tool import run_command
    result = run_command(req.cmd)
    return {"result": result}