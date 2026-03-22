"""
kdev_memory.py — Always-On Memory Layer for KDEV
Ported from: GoogleCloudPlatform/generative-ai/.../always-on-memory-agent
Original used: Google ADK + Gemini Flash-Lite
This port uses: pure Python + SQLite + Ollama (zero new deps)

DB:      ~/.kdev/memory.db
Model:   huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M
Ollama:  http://localhost:11434

Integration points in kdev_web.py:
  1. build_messages()        → prepend query_memory(user_msg) into system prompt
  2. after stream() done     → asyncio.create_task(ingest_memory(user_msg, assistant_response))
  3. app startup             → asyncio.create_task(consolidation_loop())
"""

import asyncio
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────

OLLAMA_URL   = "http://localhost:11434/api/generate"
MODEL        = "huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M"
DB_PATH      = Path.home() / ".kdev" / "memory.db"
CONSOLIDATE_INTERVAL_MINUTES = 30
LOG_PREFIX   = "[memory]"

log = logging.getLogger("kdev_memory")

# ── Database ──────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            source        TEXT    NOT NULL DEFAULT '',
            raw_text      TEXT    NOT NULL,
            summary       TEXT    NOT NULL,
            entities      TEXT    NOT NULL DEFAULT '[]',
            topics        TEXT    NOT NULL DEFAULT '[]',
            connections   TEXT    NOT NULL DEFAULT '[]',
            importance    REAL    NOT NULL DEFAULT 0.5,
            created_at    TEXT    NOT NULL,
            consolidated  INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS consolidations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source_ids  TEXT NOT NULL,
            summary     TEXT NOT NULL,
            insight     TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );
    """)
    db.commit()
    return db


def store_memory(raw_text: str, summary: str, entities: list,
                 topics: list, importance: float, source: str = "") -> int:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        """INSERT INTO memories
               (source, raw_text, summary, entities, topics, importance, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (source, raw_text, summary,
         json.dumps(entities), json.dumps(topics), importance, now),
    )
    db.commit()
    mid = cur.lastrowid
    db.close()
    log.info(f"{LOG_PREFIX} stored memory #{mid}: {summary[:60]}...")
    return mid


def read_all_memories(limit: int = 50) -> list:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    result = []
    for r in rows:
        result.append({
            "id":          r["id"],
            "source":      r["source"],
            "summary":     r["summary"],
            "entities":    json.loads(r["entities"]),
            "topics":      json.loads(r["topics"]),
            "importance":  r["importance"],
            "connections": json.loads(r["connections"]),
            "created_at":  r["created_at"],
            "consolidated": bool(r["consolidated"]),
        })
    db.close()
    return result


def read_unconsolidated_memories(limit: int = 10) -> list:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM memories WHERE consolidated = 0 ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    result = []
    for r in rows:
        result.append({
            "id":         r["id"],
            "summary":    r["summary"],
            "entities":   json.loads(r["entities"]),
            "topics":     json.loads(r["topics"]),
            "importance": r["importance"],
        })
    db.close()
    return result


def store_consolidation(source_ids: list, summary: str, insight: str) -> None:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO consolidations (source_ids, summary, insight, created_at) VALUES (?, ?, ?, ?)",
        (json.dumps(source_ids), summary, insight, now),
    )
    placeholders = ",".join("?" * len(source_ids))
    db.execute(
        f"UPDATE memories SET consolidated = 1 WHERE id IN ({placeholders})",
        source_ids,
    )
    db.commit()
    db.close()
    log.info(f"{LOG_PREFIX} consolidated {len(source_ids)} memories. insight: {insight[:80]}...")


def read_consolidation_history(limit: int = 10) -> list:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM consolidations ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    result = [{"summary": r["summary"], "insight": r["insight"],
               "source_ids": json.loads(r["source_ids"])} for r in rows]
    db.close()
    return result


def get_memory_stats() -> dict:
    db = get_db()
    total          = db.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
    unconsolidated = db.execute("SELECT COUNT(*) as c FROM memories WHERE consolidated = 0").fetchone()["c"]
    consolidations = db.execute("SELECT COUNT(*) as c FROM consolidations").fetchone()["c"]
    db.close()
    return {"total_memories": total, "unconsolidated": unconsolidated,
            "consolidations": consolidations}


# ── Ollama helper ─────────────────────────────────────────────────────────────

def _ollama(prompt: str, expect_json: bool = False) -> str:
    """Synchronous Ollama call. Runs in executor to avoid blocking the event loop."""
    payload = {
        "model":  MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if expect_json:
        payload["format"] = "json"
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=120)
        r.raise_for_status()
        return r.json().get("response", "").strip()
    except Exception as e:
        log.error(f"{LOG_PREFIX} ollama error: {e}")
        return ""


# ── IngestAgent ───────────────────────────────────────────────────────────────

async def ingest_memory(user_msg: str, assistant_response: str) -> None:
    """
    Called after every KDEV response via asyncio.create_task().
    Extracts structured memory from the exchange and stores it.
    Never blocks the response stream.
    """
    raw = f"USER: {user_msg}\nASSISTANT: {assistant_response}"

    prompt = f"""You are a memory ingest agent. Analyse this conversation exchange and extract structured memory.

Exchange:
{raw[:3000]}

Respond ONLY with valid JSON, no markdown, no explanation:
{{
  "summary": "1-2 sentence summary of what was discussed or decided",
  "entities": ["list", "of", "key", "people", "tools", "files", "concepts"],
  "topics": ["2-4", "topic", "tags"],
  "importance": 0.0
}}

importance scale: 0.8+ for decisions/patches/architecture. 0.5 for technical discussion. 0.3 for trivial chatter.
"""

    loop = asyncio.get_event_loop()
    raw_json = await loop.run_in_executor(None, lambda: _ollama(prompt, expect_json=True))

    try:
        data       = json.loads(raw_json)
        summary    = data.get("summary", "")[:300]
        entities   = data.get("entities", [])[:10]
        topics     = data.get("topics", [])[:4]
        importance = float(data.get("importance", 0.5))
        if summary:
            store_memory(raw[:2000], summary, entities, topics, importance, source="kdev-chat")
    except Exception as e:
        log.warning(f"{LOG_PREFIX} ingest parse error: {e} | raw: {raw_json[:200]}")


# ── ConsolidateAgent ──────────────────────────────────────────────────────────

async def run_consolidation() -> None:
    """
    Reads unconsolidated memories, finds patterns, stores insight.
    Called by consolidation_loop() every 30 min.
    Also hooked into /compress as the manual override trigger.
    """
    memories = read_unconsolidated_memories()
    if len(memories) < 2:
        log.info(f"{LOG_PREFIX} consolidation skipped ({len(memories)} unconsolidated)")
        return

    mem_block = "\n".join(
        f"[Memory #{m['id']}] {m['summary']} (topics: {', '.join(m['topics'])})"
        for m in memories
    )

    prompt = f"""You are a memory consolidation agent. Review these unconsolidated memories and find patterns.

Memories:
{mem_block}

Respond ONLY with valid JSON, no markdown, no explanation:
{{
  "summary": "synthesised summary across all memories",
  "insight": "one key cross-cutting pattern or insight discovered"
}}
"""

    loop = asyncio.get_event_loop()
    raw_json = await loop.run_in_executor(None, lambda: _ollama(prompt, expect_json=True))

    try:
        data    = json.loads(raw_json)
        summary = data.get("summary", "")[:500]
        insight = data.get("insight", "")[:300]
        ids     = [m["id"] for m in memories]
        if summary and insight:
            store_consolidation(ids, summary, insight)
    except Exception as e:
        log.warning(f"{LOG_PREFIX} consolidation parse error: {e} | raw: {raw_json[:200]}")


async def consolidation_loop() -> None:
    """Background task. Runs forever, consolidates every 30 min if enough memories exist."""
    log.info(f"{LOG_PREFIX} consolidation loop started (every {CONSOLIDATE_INTERVAL_MINUTES} min)")
    while True:
        await asyncio.sleep(CONSOLIDATE_INTERVAL_MINUTES * 60)
        try:
            await run_consolidation()
        except Exception as e:
            log.error(f"{LOG_PREFIX} consolidation loop error: {e}")


# ── QueryAgent ────────────────────────────────────────────────────────────────

def query_memory(user_msg: str, max_memories: int = 5) -> str:
    """
    Called synchronously inside build_messages() before the Ollama call.
    Returns a formatted block to prepend into the system prompt.
    Returns '' if nothing relevant found — no injection, no noise.
    """
    memories       = read_all_memories(limit=30)
    consolidations = read_consolidation_history(limit=5)

    if not memories:
        return ""

    # Keyword relevance filter — same approach as load_relevant_skills()
    query_words = set(user_msg.lower().split())
    scored = []
    for m in memories:
        mem_words = set(
            (m["summary"] + " " + " ".join(m["topics"]) + " " + " ".join(m["entities"])).lower().split()
        )
        score = len(query_words & mem_words) + m["importance"]
        if score > 0:
            scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [m for _, m in scored[:max_memories]]

    if not top:
        return ""

    lines = ["## Relevant Memory Context"]
    for m in top:
        lines.append(f"- [#{m['id']}] {m['summary']}")

    if consolidations:
        lines.append("\n## Past Insights")
        for c in consolidations[:2]:
            lines.append(f"- {c['insight']}")

    return "\n".join(lines)
