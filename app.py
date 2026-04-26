from fastapi import FastAPI
from pydantic import BaseModel
from agent import run_agent

app = FastAPI()

class Request(BaseModel):
    message: str

@app.post("/chat")
def chat(req: Request):
    result = run_agent(req.message)
    return {"response": result}