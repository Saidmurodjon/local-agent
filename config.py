import os
import psutil
import requests as _req

OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_URL  = OLLAMA_BASE + "/api/generate"

# Preferred coding models in order. First one found in Ollama is used.
_PREFERRED = [
    "qwen2.5-coder:7b",
    "qwen2.5-coder:3b",
    "qwen2.5-coder:1.5b",
    "qwen2.5:7b",
    "qwen2.5:3b",
    "codellama:7b",
    "llama3:8b",
]

def detect_model() -> str:
    """Return best available Ollama model, or env override."""
    env = os.getenv("OLLAMA_MODEL", "")
    if env:
        return env
    try:
        r = _req.get(OLLAMA_BASE + "/api/tags", timeout=5)
        if r.ok:
            installed = {m["name"] for m in r.json().get("models", [])}
            for p in _PREFERRED:
                if p in installed:
                    return p
            # fallback: first installed model
            if installed:
                return next(iter(installed))
    except Exception:
        pass
    return "qwen2.5-coder:3b"  # safe default

def list_ollama_models() -> list[str]:
    try:
        r = _req.get(OLLAMA_BASE + "/api/tags", timeout=5)
        if r.ok:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []

MODEL = detect_model()

RAM_GB    = psutil.virtual_memory().total / (1024**3)
CPU_CORES = psutil.cpu_count(logical=False) or 4

OLLAMA_OPTIONS = {
    "num_ctx":        8192 if RAM_GB >= 12 else 4096,
    "num_thread":     min(CPU_CORES * 2, 8),
    "num_gpu":        18,
    "temperature":    0.1,
    "top_p":          0.9,
    "repeat_penalty": 1.1,
    "num_predict":    2048,
    "low_vram":       True,
}

WORKSPACE_DIR = "./workspace"
MAX_RETRIES   = 4
MAX_STEPS     = 20
GIT_AUTO_PUSH = True
