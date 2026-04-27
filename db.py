"""
Local Agent V12 — SQLite database layer.
All state lives in workspace/agent.db (one file, portable).
"""
import sqlite3
import os
import json
import time
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.abspath("./workspace"), "agent.db")


# ──────────────────────────── connection ──────────────────────────────────────

@contextmanager
def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ──────────────────────────── schema ─────────────────────────────────────────

def init_db():
    with _conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            folder      TEXT,
            model       TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT NOT NULL,
            role        TEXT NOT NULL,        -- user | assistant | system | log
            content     TEXT NOT NULL,
            msg_type    TEXT DEFAULT 'chat',  -- chat | log | tool | error
            created_at  TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT,
            name        TEXT,
            folder      TEXT,
            files       TEXT,   -- JSON array
            status      TEXT,   -- success | failed
            stdout      TEXT,
            stderr      TEXT,
            created_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS fine_tune_samples (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt      TEXT NOT NULL,
            completion  TEXT NOT NULL,
            quality     INTEGER DEFAULT 3,  -- 1-5
            category    TEXT,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fine_tune_jobs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            base_model      TEXT NOT NULL,
            system_prompt   TEXT,
            status          TEXT DEFAULT 'pending',
            samples_count   INTEGER DEFAULT 0,
            output_path     TEXT,
            log             TEXT,
            created_at      TEXT NOT NULL,
            completed_at    TEXT
        );
        """)
        # migration: add model column if missing
        cols = [r[1] for r in con.execute("PRAGMA table_info(sessions)").fetchall()]
        if "model" not in cols:
            con.execute("ALTER TABLE sessions ADD COLUMN model TEXT")


# ──────────────────────────── sessions ───────────────────────────────────────

def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def session_create(name: str, folder: str = None, model: str = None) -> dict:
    sid = str(int(time.time() * 1000))
    folder = folder or os.path.abspath(f"./workspace/sessions/{sid}")
    os.makedirs(folder, exist_ok=True)
    now = _now()
    with _conn() as con:
        con.execute(
            "INSERT INTO sessions (id,name,folder,model,created_at,updated_at) VALUES (?,?,?,?,?,?)",
            (sid, name, folder, model, now, now),
        )
    return session_get(sid)


def session_get(sid: str) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    if not row:
        return None
    return dict(row)


def session_list() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT s.*, (SELECT content FROM messages WHERE session_id=s.id "
            "ORDER BY id DESC LIMIT 1) as last_msg "
            "FROM sessions s ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def session_update(sid: str, **kwargs):
    kwargs["updated_at"] = _now()
    sets  = ", ".join(f"{k}=?" for k in kwargs)
    vals  = list(kwargs.values()) + [sid]
    with _conn() as con:
        con.execute(f"UPDATE sessions SET {sets} WHERE id=?", vals)


def session_delete(sid: str):
    with _conn() as con:
        con.execute("DELETE FROM sessions WHERE id=?", (sid,))


# ──────────────────────────── messages ───────────────────────────────────────

def msg_add(session_id: str, role: str, content: str, msg_type: str = "chat") -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO messages (session_id,role,content,msg_type,created_at) VALUES (?,?,?,?,?)",
            (session_id, role, content, msg_type, _now()),
        )
        lid = cur.lastrowid
    session_update(session_id, updated_at=_now())
    return lid


def msg_list(session_id: str, limit: int = 200) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def msg_context(session_id: str, n: int = 8) -> str:
    """Return last n chat messages as context string."""
    with _conn() as con:
        rows = con.execute(
            "SELECT role,content FROM messages WHERE session_id=? AND msg_type='chat' "
            "ORDER BY id DESC LIMIT ?",
            (session_id, n),
        ).fetchall()
    ctx = ""
    for r in reversed(rows):
        ctx += f"\n{r['role'].upper()}: {r['content'][:400]}\n"
    return ctx


# ──────────────────────────── projects ───────────────────────────────────────

def project_save(session_id: str, name: str, folder: str, files: list,
                 status: str, stdout: str, stderr: str) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO projects (session_id,name,folder,files,status,stdout,stderr,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (session_id, name, folder, json.dumps(files), status, stdout[:2000], stderr[:500], _now()),
        )
        return cur.lastrowid


# ──────────────────────────── fine-tune samples ───────────────────────────────

def ft_add_sample(prompt: str, completion: str, quality: int = 3, category: str = None) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO fine_tune_samples (prompt,completion,quality,category,created_at)"
            " VALUES (?,?,?,?,?)",
            (prompt, completion, quality, category, _now()),
        )
        return cur.lastrowid


def ft_list_samples(limit: int = 500) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM fine_tune_samples ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def ft_rate_sample(sample_id: int, quality: int):
    with _conn() as con:
        con.execute("UPDATE fine_tune_samples SET quality=? WHERE id=?", (quality, sample_id))


def ft_delete_sample(sample_id: int):
    with _conn() as con:
        con.execute("DELETE FROM fine_tune_samples WHERE id=?", (sample_id,))


def ft_export_jsonl(path: str, min_quality: int = 3) -> int:
    samples = [s for s in ft_list_samples() if s["quality"] >= min_quality]
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps({
                "messages": [
                    {"role": "system",  "content": "You are an expert Python coding assistant."},
                    {"role": "user",    "content": s["prompt"]},
                    {"role": "assistant","content": s["completion"]},
                ]
            }, ensure_ascii=False) + "\n")
    return len(samples)


# ──────────────────────────── fine-tune jobs ──────────────────────────────────

def ft_create_job(name: str, base_model: str, system_prompt: str, samples_count: int) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO fine_tune_jobs (name,base_model,system_prompt,samples_count,created_at)"
            " VALUES (?,?,?,?,?)",
            (name, base_model, system_prompt, samples_count, _now()),
        )
        return cur.lastrowid


def ft_update_job(job_id: int, **kwargs):
    if "completed_at" not in kwargs and kwargs.get("status") in ("done", "failed"):
        kwargs["completed_at"] = _now()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [job_id]
    with _conn() as con:
        con.execute(f"UPDATE fine_tune_jobs SET {sets} WHERE id=?", vals)


def ft_list_jobs() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM fine_tune_jobs ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


# ──────────────────────────── init on import ─────────────────────────────────
init_db()
