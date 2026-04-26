from fastapi import FastAPI
from pydantic import BaseModel
from agent import run_agent
from tools.terminal_tool import run_command

app = FastAPI()

class Request(BaseModel):
    message: str

class ConfirmRequest(BaseModel):
    cmd: str

@app.post("/chat")
def chat(req: Request):
    result = run_agent(req.message)
    return {"response": result}

@app.post("/confirm")
def confirm(req: ConfirmRequest):
    result = run_command(req.cmd)
    return {
        "status": "done",
        "result": result
    }