import os

WORKSPACE = "./workspace"

def read_file(path: str):
    full_path = os.path.join(WORKSPACE, path)

    if not os.path.exists(full_path):
        return "File not found"

    with open(full_path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str):
    full_path = os.path.join(WORKSPACE, path)

    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    return f"File written: {path}"