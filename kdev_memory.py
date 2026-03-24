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
            session_id    TEXT    NOT NULL DEFAULT '',
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
        CREATE TABLE IF NOT EXISTS memory_nodes (
            session_id  TEXT    NOT NULL,
            path        TEXT    NOT NULL,
            gist        TEXT    NOT NULL DEFAULT '',
            content     TEXT,
            is_dir      INTEGER NOT NULL DEFAULT 0,
            created_at  INTEGER NOT NULL,
            updated_at  INTEGER NOT NULL,
            PRIMARY KEY (session_id, path)
        );
        CREATE INDEX IF NOT EXISTS idx_memory_nodes_session
            ON memory_nodes (session_id, path);
    """)
    try:
        db.execute("ALTER TABLE memories ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass  # column already exists
    db.commit()
    return db


def store_memory(raw_text: str, summary: str, entities: list,
                 topics: list, importance: float, source: str = "",
                 session_id: str = "") -> int:
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        """INSERT INTO memories
               (source, session_id, raw_text, summary, entities, topics, importance, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (source, session_id, raw_text, summary,
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


# -- VFS Memory (ported from snoglobe/helios memory-store + global-memory) --

import time as _time

def _vfs_validate_path(path: str) -> str:
    if not path.startswith('/'):
        path = '/' + path
    parts = path.split('/')
    resolved = []
    for p in parts:
        if p == '..':
            if resolved:
                resolved.pop()
        elif p not in ('', '.'):
            resolved.append(p)
    tail = '/' if (path.endswith('/') and resolved) else ''
    return '/' + '/'.join(resolved) + tail

def _vfs_normalize_dir(path: str) -> str:
    if path == '/':
        return '/'
    return path if path.endswith('/') else path + '/'


class MemoryVFS:
    def __init__(self, session_id: str):
        self.session_id = session_id

    def _db(self):
        return get_db()

    def ls(self, dir_path: str = '/') -> list:
        normalized = _vfs_normalize_dir(_vfs_validate_path(dir_path))
        prefix_len = len(normalized)
        db = self._db()
        rows = db.execute(
            'SELECT path, gist, is_dir, created_at, updated_at'
            ' FROM memory_nodes'
            ' WHERE session_id = ? AND path LIKE ? AND path != ?',
            (self.session_id, normalized + '%', normalized)
        ).fetchall()
        db.close()
        result = []
        for r in rows:
            rel = r['path'][prefix_len:]
            if '/' not in rel or (rel.endswith('/') and '/' not in rel[:-1]):
                result.append(dict(r))
        return result

    def tree(self, dir_path: str = '/') -> list:
        normalized = _vfs_normalize_dir(_vfs_validate_path(dir_path))
        db = self._db()
        rows = db.execute(
            'SELECT path, gist, is_dir FROM memory_nodes'
            ' WHERE session_id = ? AND path LIKE ? AND path != ?'
            ' ORDER BY path',
            (self.session_id, normalized + '%', normalized)
        ).fetchall()
        db.close()
        return [dict(r) for r in rows]

    def read(self, path: str):
        path = _vfs_validate_path(path)
        db = self._db()
        row = db.execute(
            'SELECT path, gist, content, is_dir, created_at, updated_at'
            ' FROM memory_nodes WHERE session_id = ? AND path = ?',
            (self.session_id, path)
        ).fetchone()
        db.close()
        return dict(row) if row else None

    def write(self, path: str, gist: str, content=None) -> None:
        path = _vfs_validate_path(path)
        now = int(_time.time() * 1000)
        is_dir = 1 if content is None else 0
        self._ensure_parents(path)
        db = self._db()
        db.execute(
            'INSERT INTO memory_nodes'
            ' (session_id, path, gist, content, is_dir, created_at, updated_at)'
            ' VALUES (?, ?, ?, ?, ?, ?, ?)'
            ' ON CONFLICT(session_id, path) DO UPDATE SET'
            ' gist=excluded.gist, content=excluded.content,'
            ' is_dir=excluded.is_dir, updated_at=excluded.updated_at',
            (self.session_id, path, gist, content, is_dir, now, now)
        )
        db.commit()
        db.close()

    def rm(self, path: str) -> int:
        path = _vfs_validate_path(path)
        like = (path + '%') if path.endswith('/') else (path + '/%')
        db = self._db()
        result = db.execute(
            'DELETE FROM memory_nodes WHERE session_id = ? AND (path = ? OR path LIKE ?)',
            (self.session_id, path, like)
        )
        db.commit()
        count = result.rowcount
        db.close()
        return count

    def exists(self, path: str) -> bool:
        path = _vfs_validate_path(path)
        db = self._db()
        row = db.execute(
            'SELECT 1 FROM memory_nodes WHERE session_id = ? AND path = ?',
            (self.session_id, path)
        ).fetchone()
        db.close()
        return row is not None

    def count(self) -> int:
        db = self._db()
        row = db.execute(
            'SELECT COUNT(*) as c FROM memory_nodes WHERE session_id = ?',
            (self.session_id,)
        ).fetchone()
        db.close()
        return row['c']

    def format_tree(self, dir_path: str = '/') -> str:
        nodes = self.tree(dir_path)
        if not nodes:
            return '(empty)'
        lines = []
        for node in nodes:
            parts = [p for p in node['path'].split('/') if p]
            depth = len(parts) - 1
            indent = '  ' * depth
            name = parts[-1] + ('/' if node['is_dir'] else '')
            lines.append(indent + name + ': ' + node['gist'])
        return '\n'.join(lines)

    def clear(self) -> None:
        db = self._db()
        db.execute('DELETE FROM memory_nodes WHERE session_id = ?', (self.session_id,))
        db.commit()
        db.close()

    def _ensure_parents(self, path: str) -> None:
        parts = [p for p in path.split('/') if p]
        if len(parts) <= 1:
            return
        now = int(_time.time() * 1000)
        db = self._db()
        for i in range(1, len(parts)):
            parent_path = '/' + '/'.join(parts[:i]) + '/'
            db.execute(
                'INSERT OR IGNORE INTO memory_nodes'
                ' (session_id, path, gist, content, is_dir, created_at, updated_at)'
                ' VALUES (?, ?, ?, NULL, 1, ?, ?)',
                (self.session_id, parent_path, parts[i - 1], now, now)
            )
        db.commit()
        db.close()


_GLOBAL_SESSION_ID = '__global__'
_GLOBAL_PREFIX     = '/global/'


class GlobalMemoryVFS(MemoryVFS):
    def __init__(self, session_id: str):
        super().__init__(session_id)
        self._global = MemoryVFS(_GLOBAL_SESSION_ID)

    def _is_global(self, path: str) -> bool:
        return path in ('/global/', '/global') or path.startswith(_GLOBAL_PREFIX)

    def _to_global_path(self, path: str) -> str:
        if path in ('/global/', '/global'):
            return '/'
        return path[len(_GLOBAL_PREFIX) - 1:]

    def _from_global_path(self, path: str) -> str:
        if path == '/':
            return '/global/'
        return '/global' + path

    def _map_node(self, node: dict) -> dict:
        return dict(node, path=self._from_global_path(node['path']))

    def ls(self, dir_path: str = '/') -> list:
        if dir_path == '/':
            session_children = super().ls('/')
            has_global = self._global.count() > 0
            has_global_dir = any(n['path'] == '/global/' for n in session_children)
            if has_global and not has_global_dir:
                synthetic = {'path': '/global/', 'gist': 'shared knowledge (persists across sessions)',
                             'content': None, 'is_dir': 1, 'created_at': 0, 'updated_at': 0}
                return [synthetic] + [n for n in session_children if not n['path'].startswith('/global')]
            return session_children
        if self._is_global(dir_path):
            return [self._map_node(n) for n in self._global.ls(self._to_global_path(dir_path))]
        return super().ls(dir_path)

    def tree(self, dir_path: str = '/') -> list:
        if dir_path in ('/', ''):
            session_tree = super().tree('/')
            global_tree  = [self._map_node(n) for n in self._global.tree('/')]
            return sorted(global_tree + session_tree, key=lambda n: n['path'])
        if self._is_global(dir_path):
            return [self._map_node(n) for n in self._global.tree(self._to_global_path(dir_path))]
        return super().tree(dir_path)

    def read(self, path: str):
        if self._is_global(path):
            node = self._global.read(self._to_global_path(path))
            return self._map_node(node) if node else None
        return super().read(path)

    def write(self, path: str, gist: str, content=None) -> None:
        if self._is_global(path):
            self._global.write(self._to_global_path(path), gist, content)
            return
        super().write(path, gist, content)

    def rm(self, path: str) -> int:
        if self._is_global(path):
            return self._global.rm(self._to_global_path(path))
        return super().rm(path)

    def exists(self, path: str) -> bool:
        if self._is_global(path):
            return self._global.exists(self._to_global_path(path))
        return super().exists(path)

    def count(self) -> int:
        return super().count() + self._global.count()


def vfs_get(session_id: str) -> GlobalMemoryVFS:
    return GlobalMemoryVFS(session_id)


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

async def ingest_memory(user_msg: str, assistant_response: str, session_id: str = "", agent_run_id: str = "") -> None:
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
            store_memory(raw[:2000], summary, entities, topics, importance, source="kdev-chat", session_id=session_id)
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
