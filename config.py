OLLAMA_URL = "http://localhost:11434/api/generate"

MODEL = "qwen2.5-coder:3b"
# Agar 7B sekin bo‘lsa 3B qoldiring
# MODEL = "qwen2.5-coder:7b"

WORKSPACE = "./workspace"

OLLAMA_OPTIONS = {
    "temperature": 0.2,
    "num_ctx": 4096,
    "num_predict": 1400,
    "num_thread": 6
}