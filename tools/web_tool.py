import os

WEB_TEMPLATES = {
    "flask": {
        "app.py": '''from flask import Flask, render_template, jsonify
import os

app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def status():
    return jsonify({"status": "running", "version": "1.0"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=False, host="0.0.0.0", port=port)
''',
        "templates/index.html": '''<!DOCTYPE html>
<html>
<head><title>Flask App</title>
<style>body{font-family:sans-serif;max-width:800px;margin:50px auto;padding:20px}</style>
</head>
<body>
<h1>Flask App Running</h1>
<p>Server is live at <a href="/api/status">/api/status</a></p>
</body>
</html>''',
        "requirements.txt": "flask>=3.0.0\n",
        "README.md": "# Flask App\n\n## Run\n```\npip install -r requirements.txt\npython app.py\n```\n",
        ".gitignore": "__pycache__/\n*.pyc\n.env\n.venv/\n",
    },
    "html": {
        "index.html": '''<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Web Sahifa</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: "Segoe UI", sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
.container { max-width: 1000px; margin: 0 auto; padding: 40px 20px; }
h1 { font-size: 2.5rem; color: #38bdf8; margin-bottom: 20px; }
.card { background: #1e293b; border-radius: 12px; padding: 24px; margin: 16px 0; }
</style>
</head>
<body>
<div class="container">
  <h1>AI Agent Web</h1>
  <div class="card">
    <h2>Status: Active</h2>
    <p>Local Agent running on Core i5 / 12GB RAM</p>
  </div>
</div>
<script>
  document.querySelector(".card p").textContent += " | " + new Date().toLocaleString();
</script>
</body>
</html>''',
    },
}


def create_web_project(name: str, project_type: str = "flask") -> dict:
    base_path = f"./workspace/{name}"
    os.makedirs(base_path, exist_ok=True)

    template = WEB_TEMPLATES.get(project_type, WEB_TEMPLATES["html"])
    created = []

    for filepath, content in template.items():
        full_path = os.path.join(base_path, filepath)
        dir_part = os.path.dirname(full_path)
        if dir_part:
            os.makedirs(dir_part, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        created.append(filepath)

    return {
        "returncode": 0,
        "stdout": f"Created {project_type} project '{name}' with files: {', '.join(created)}",
        "stderr": "",
    }
