# Local Agent V11

**Hardware:** Core i5 10th Gen | 12GB RAM | NVIDIA MX 330 2GB
**Model:** qwen2.5-coder:7b (Ollama)

## Setup

```bash
# 1. Ollama o'rnatish
winget install Ollama.Ollama

# 2. Model yuklab olish
ollama pull qwen2.5-coder:7b

# 3. Dependencies
pip install -r requirements.txt

# 4. Agent ishga tushirish
python app.py
# -> http://localhost:5000
```

## Features V11
- Avtomatik kod yaratish + tuzatish (4x retry)
- Flask/HTML web loyiha yaratish
- Python package auto-install
- GitHub versioning (git commit/push)
- GPU optimization (MX 330 - 18 layers offload)
- Semantic versioning (V1, V2, V3...)
- Real-time web UI (localhost:5000)
- Workspace file browser
- Background task execution with live log streaming

## GitHub Push
Web UI -> GitHub Push panel -> repo URL kiriting -> Push

## Versioning
```
V11.0 — Base upgrade
V11.1 — Bug fixes
V11.2 — New tools added
V12.0 — Major feature
```
