"""Local Agent V12 — configuration."""
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
            if installed:
                return next(iter(installed))
    except Exception:
        pass
    return "qwen2.5-coder:3b"


def list_ollama_models() -> list[str]:
    try:
        r = _req.get(OLLAMA_BASE + "/api/tags", timeout=5)
        if r.ok:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


def get_gpu_info() -> dict:
    """Return GPU info: vram_total, vram_used, cuda, ollama_using_gpu."""
    info = {"vram_total": 0, "vram_used": 0, "vram_free": 0,
            "cuda": False, "ollama_using_gpu": False,
            "name": "Unknown", "driver": "", "tok_per_sec": 0}
    try:
        import subprocess
        r = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,memory.used,memory.free,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            parts = [p.strip() for p in r.stdout.strip().split(",")]
            info["name"]       = parts[0]
            info["vram_total"] = int(parts[1])
            info["vram_used"]  = int(parts[2])
            info["vram_free"]  = int(parts[3])
            info["driver"]     = parts[4]
            info["cuda"]       = True
    except Exception:
        pass

    # Check if Ollama is actually using VRAM
    try:
        ps = _req.get(OLLAMA_BASE + "/api/ps", timeout=3).json()
        for m in ps.get("models", []):
            if m.get("size_vram", 0) > 0:
                info["ollama_using_gpu"] = True
                info["vram_used_ollama"] = m["size_vram"] // (1024 * 1024)
    except Exception:
        pass

    return info


MODEL     = detect_model()
RAM_GB    = psutil.virtual_memory().total / (1024 ** 3)
CPU_CORES = psutil.cpu_count(logical=False) or 4

# MX230/MX330 has 2GB VRAM. qwen2.5-coder:3b Q4 ≈ 2GB.
# We split: ~15 layers on GPU, rest on CPU to avoid OOM.
_VRAM_MB  = 0
try:
    import subprocess as _sp
    _r = _sp.run(
        ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=5
    )
    if _r.returncode == 0:
        _VRAM_MB = int(_r.stdout.strip())
except Exception:
    pass

# Safe GPU layer count: use 60% of VRAM
_GPU_LAYERS = 0
if _VRAM_MB >= 2000:
    _GPU_LAYERS = 20   # ~1.2GB of 3b model on GPU
elif _VRAM_MB >= 1000:
    _GPU_LAYERS = 10
elif _VRAM_MB > 0:
    _GPU_LAYERS = 5

OLLAMA_OPTIONS = {
    "num_ctx":        8192 if RAM_GB >= 12 else 4096,
    "num_thread":     min(CPU_CORES * 2, 8),
    "num_gpu":        _GPU_LAYERS,
    "temperature":    0.1,
    "top_p":          0.9,
    "repeat_penalty": 1.1,
    "num_predict":    4096,   # was 2048 — prevents context overflow mid-generation
    "low_vram":       True,
    "main_gpu":       0,
}

WORKSPACE_DIR = "./workspace"
MAX_RETRIES   = 4
MAX_STEPS     = 20
GIT_AUTO_PUSH = True
