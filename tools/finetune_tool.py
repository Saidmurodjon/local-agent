"""
Fine-tune tooling for Local Agent V12.

Actual gradient-based training on MX330 (2GB) is not feasible,
so we offer three approaches:
  1. Ollama specialist — Modelfile with custom SYSTEM + few-shot examples
  2. JSONL export — OpenAI/HuggingFace format for external training
  3. Sample collection — auto-saved from every successful agent run
"""
import subprocess
import os
import json
import time

import db


MODELFILE_TEMPLATE = """FROM {base_model}

SYSTEM \"\"\"{system_prompt}\"\"\"

{parameter_block}
"""

PARAM_DEFAULTS = """
PARAMETER temperature 0.05
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
PARAMETER num_ctx 4096
""".strip()


# ─────────────────────────── sample helpers ──────────────────────────────────

def collect_sample(prompt: str, completion: str, quality: int = 4, category: str = "code") -> int:
    """Save a prompt/completion pair to the fine-tune pool."""
    return db.ft_add_sample(prompt, completion, quality, category)


def export_jsonl(output_path: str = None, min_quality: int = 3) -> dict:
    """Export collected samples as JSONL (OpenAI chat format)."""
    if not output_path:
        output_path = os.path.abspath(
            f"./workspace/finetune/dataset_{int(time.time())}.jsonl"
        )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    count = db.ft_export_jsonl(output_path, min_quality)
    return {
        "path": output_path,
        "count": count,
        "min_quality": min_quality,
    }


# ─────────────────────────── Ollama specialist ───────────────────────────────

def build_system_prompt(base: str, examples: list[dict]) -> str:
    """Build an enriched system prompt with few-shot examples."""
    prompt = base.strip()
    if examples:
        prompt += "\n\n## Examples\n"
        for i, ex in enumerate(examples[:5], 1):
            prompt += f"\n### Example {i}\nUser: {ex['prompt'][:300]}\nAssistant: {ex['completion'][:500]}\n"
    return prompt


def create_ollama_specialist(
    name: str,
    base_model: str,
    domain: str,
    extra_instructions: str = "",
    min_quality: int = 4,
) -> dict:
    """
    Create a specialist Ollama model using Modelfile.
    Uses collected fine-tune samples as few-shot examples in the SYSTEM prompt.
    """
    # Gather high-quality samples as examples
    all_samples = [s for s in db.ft_list_samples(100) if s["quality"] >= min_quality]
    # Pick up to 5 domain-matching examples
    domain_samples = [s for s in all_samples if s.get("category") == domain][:5]
    fallback_samples = all_samples[:5]
    examples = domain_samples or fallback_samples

    base_system = f"""You are a specialist AI coding assistant focused on: {domain}.

{extra_instructions}

You run on Intel Core i5 10th Gen with 12GB RAM and NVIDIA MX330 GPU.
Always write clean, efficient Python/JavaScript code.
Never use input(), infinite loops, or heavy ML libraries.
Programs must run automatically and produce demo output."""

    system_prompt = build_system_prompt(base_system, examples)

    # Write Modelfile
    modelfile_dir  = os.path.abspath("./workspace/finetune/models")
    os.makedirs(modelfile_dir, exist_ok=True)
    modelfile_path = os.path.join(modelfile_dir, f"{name}.Modelfile")

    modelfile_content = MODELFILE_TEMPLATE.format(
        base_model=base_model,
        system_prompt=system_prompt.replace('"', '\\"'),
        parameter_block=PARAM_DEFAULTS,
    )
    with open(modelfile_path, "w", encoding="utf-8") as f:
        f.write(modelfile_content)

    # Register job in DB
    job_id = db.ft_create_job(
        name=name,
        base_model=base_model,
        system_prompt=system_prompt,
        samples_count=len(examples),
    )
    db.ft_update_job(job_id, status="running", output_path=modelfile_path)

    # Run `ollama create`
    try:
        result = subprocess.run(
            ["ollama", "create", name, "-f", modelfile_path],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            db.ft_update_job(job_id, status="done",
                             log=f"OK: {result.stdout[:500]}")
            return {
                "ok": True, "job_id": job_id,
                "model": name,
                "examples_used": len(examples),
                "modelfile": modelfile_path,
                "stdout": result.stdout[:1000],
            }
        else:
            db.ft_update_job(job_id, status="failed",
                             log=result.stderr[:500])
            return {
                "ok": False, "job_id": job_id,
                "error": result.stderr[:500],
                "modelfile": modelfile_path,
            }
    except FileNotFoundError:
        db.ft_update_job(job_id, status="failed", log="ollama CLI not found in PATH")
        return {"ok": False, "error": "ollama CLI not found"}
    except subprocess.TimeoutExpired:
        db.ft_update_job(job_id, status="failed", log="Timeout 300s")
        return {"ok": False, "error": "Timeout creating model"}


def list_custom_models() -> list[str]:
    """Return list of custom (non-library) Ollama models."""
    try:
        import requests, config
        r = requests.get(config.OLLAMA_BASE + "/api/tags", timeout=5)
        if r.ok:
            return [m["name"] for m in r.json().get("models", [])
                    if ":" in m["name"]]
    except Exception:
        pass
    return []
