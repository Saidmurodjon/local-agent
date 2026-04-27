import os
import psutil

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

RAM_GB = psutil.virtual_memory().total / (1024**3)
CPU_CORES = psutil.cpu_count(logical=False) or 4

OLLAMA_OPTIONS = {
    "num_ctx": 8192 if RAM_GB >= 12 else 4096,
    "num_thread": min(CPU_CORES * 2, 8),
    "num_gpu": 18,
    "temperature": 0.1,
    "top_p": 0.9,
    "repeat_penalty": 1.1,
    "num_predict": 2048,
    "low_vram": True,
}

WORKSPACE_DIR = "./workspace"
MAX_RETRIES = 4
MAX_STEPS = 20
GIT_AUTO_PUSH = True
