"""
skills.py — Self-learning loop for kdev.

Three systems working together:

1. TRACE ANALYSIS
   After every agent run, inspect the message history to count tool calls,
   API rounds, and detect patterns (redundant reads, dead-end searches, etc.)

2. SKILL DOCUMENTS
   When a task was complex enough (>=4 tool calls or >=3 API rounds), ask the
   LLM to distill the solution into a reusable SKILL.md file saved under
   ~/.kdev/skills/. Next session the relevant skills are keyword-matched and
   injected into the system prompt — agent learns from its own history.

3. SESSION COMPRESSION  (/compress command)
   At end-of-session, distill the entire conversation using the knowledge
   distillation technique:
     - Key decisions made this session
     - Patterns and approaches that worked
     - Any new skills discovered
     - Compact memory update for .agent.md
   Result is saved as a compressed session snapshot — future sessions start
   with this context instead of re-reading raw history.
"""

from __future__ import annotations

import json
import os
import re
import httpx
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Dirs ───────────────────────────────────────────────────────────────────────
HOME       = Path.home()
KDEV_DIR   = HOME / ".kdev"
SKILLS_DIR = KDEV_DIR / "skills"
SKILLS_DIR.mkdir(parents=True, exist_ok=True)

# ── Secret redaction ───────────────────────────────────────────────────────────
# Fernet keys: base64url, exactly 44 chars ending in '='
_FERNET_KEY_RE = re.compile(r"[A-Za-z0-9_\-]{43}=")

def _redact_secrets(text: str) -> str:
    """Replace Fernet key patterns with [VAULT_KEY_REDACTED]."""
    return _FERNET_KEY_RE.sub("[VAULT_KEY_REDACTED]", text)


# ══════════════════════════════════════════════════════════════════════════════
#  Trace Analysis
# ══════════════════════════════════════════════════════════════════════════════
class Trace:
    """Captured statistics from one agent run."""

    def __init__(self):
        self.tool_calls:  list[str] = []   # tool names in order
        self.api_rounds:  int       = 0    # how many LLM calls were made
        self.unique_tools: set[str] = set()
        self.redundant:   list[str] = []   # tools called 3+ times on same path

    @property
    def is_complex(self) -> bool:
        """Worth writing a skill doc for this run?"""
        return len(self.tool_calls) >= 4 or self.api_rounds >= 3

    def summary(self) -> str:
        counts = {}
        for t in self.tool_calls:
            counts[t] = counts.get(t, 0) + 1
        lines = [f"  API rounds : {self.api_rounds}",
                 f"  Tool calls : {len(self.tool_calls)}",
                 f"  Tools used : {', '.join(sorted(self.unique_tools)) or 'none'}"]
        redundant = [f"{t}×{n}" for t, n in counts.items() if n >= 3]
        if redundant:
            lines.append(f"  Repeated   : {', '.join(redundant)}")
        return "\n".join(lines)


def analyze_trace(new_messages: list) -> Trace:
    """
    Parse pydantic-ai new_messages() output into a Trace.
    Counts tool calls and API round-trips.
    """
    from pydantic_ai.messages import ModelResponse, ModelRequest, ToolCallPart, ToolReturnPart

    trace = Trace()
    for msg in new_messages:
        if isinstance(msg, ModelResponse):
            trace.api_rounds += 1
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    trace.tool_calls.append(part.tool_name)
                    trace.unique_tools.add(part.tool_name)
    # Flag tools used >=3 times
    counts: dict[str, int] = {}
    for t in trace.tool_calls:
        counts[t] = counts.get(t, 0) + 1
    trace.redundant = [t for t, n in counts.items() if n >= 3]
    return trace


# ══════════════════════════════════════════════════════════════════════════════
#  Direct Bedrock call (one-shot, no pydantic-ai overhead)
#  Used for skill writing and session compression — these are short LLM tasks
#  that don't need tool access or streaming.
# ══════════════════════════════════════════════════════════════════════════════
async def _bedrock_call(prompt: str, system: str = "") -> str:
    """Single non-streaming Bedrock call. Returns assistant text."""
    token  = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "").strip()
    region = os.getenv("AWS_REGION", "us-east-1")
    model  = os.getenv(
        "ANTHROPIC_DEFAULT_SONNET_MODEL", "us.anthropic.claude-sonnet-4-6"
    )

    if not token or token == "YOUR_BEARER_TOKEN_HERE":
        # Fallback: direct Anthropic key
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if anthropic_key:
            return await _anthropic_call(prompt, system, anthropic_key)
        return ""

    url  = f"https://bedrock-runtime.{region}.amazonaws.com/model/{model}/invoke"
    body: dict[str, Any] = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens":        2048,
        "messages":          [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            url, json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/json",
                "Accept":        "application/json",
            },
        )
    if resp.status_code != 200:
        return ""
    data = resp.json()
    return "".join(
        b.get("text", "") for b in data.get("content", [])
        if b.get("type") == "text"
    )


async def _anthropic_call(prompt: str, system: str, api_key: str) -> str:
    """Direct Anthropic API fallback."""
    body: dict[str, Any] = {
        "model":      "claude-sonnet-4-6",
        "max_tokens": 2048,
        "messages":   [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            json=body,
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type":      "application/json",
            },
        )
    if resp.status_code != 200:
        return ""
    return "".join(
        b.get("text", "") for b in resp.json().get("content", [])
        if b.get("type") == "text"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Skill Documents
# ══════════════════════════════════════════════════════════════════════════════
async def maybe_write_skill(
    user_task: str,
    new_messages: list,
    trace: Trace,
) -> str | None:
    """
    If the run was complex enough, ask the LLM to distill it into a skill doc.
    Returns the skill file path if written, else None.
    """
    if not trace.is_complex:
        return None

    # Build a compact trace narrative for the LLM to reason about
    tool_sequence = " → ".join(trace.tool_calls) if trace.tool_calls else "none"

    # Extract the final assistant response text
    from pydantic_ai.messages import ModelResponse, TextPart
    import re as _re
    final_response = ""
    for msg in reversed(new_messages):
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart):
                    # Strip <think>...</think> blocks — skill docs should capture
                    # the clean solution, not the internal reasoning chain
                    raw = part.content
                    cleaned = _re.sub(r"<think>.*?</think>", "", raw, flags=_re.DOTALL).strip()
                    final_response = cleaned or raw  # fallback to raw if stripping empties it
                    break
            if final_response:
                break

    prompt = f"""You are documenting a reusable skill for a coding agent.

A user asked: "{user_task}"

The agent solved it using {len(trace.tool_calls)} tool calls across {trace.api_rounds} API rounds.
Tool sequence: {tool_sequence}

The agent's final response was:
{final_response[:1500]}

Write a concise SKILL.md document that captures:
1. When to apply this skill (trigger conditions / task patterns)
2. The optimal approach / strategy (not step-by-step — the mental model)
3. Key tools to use and in what order
4. Pitfalls to avoid (if any were evident)
5. A one-line summary for search indexing

Format:
---
title: <skill name, max 8 words>
tags: <3-5 keywords, comma separated>
complexity: <simple|medium|complex>
summary: <one line>
---

## When to use
...

## Approach
...

## Tool strategy
...

## Pitfalls
...

Be terse. This will be injected into a system prompt — every word costs tokens."""

    skill_text = await _bedrock_call(
        prompt,
        system="You write precise, minimal technical documentation. No padding. No examples unless critical."
    )

    if not skill_text or len(skill_text) < 50:
        return None

    # Redact any leaked secrets before writing to disk
    skill_text = _redact_secrets(skill_text)

    # Derive filename from task
    slug = re.sub(r"[^a-z0-9]+", "-", user_task[:50].lower()).strip("-")
    ts   = datetime.now().strftime("%Y%m%d-%H%M")
    path = SKILLS_DIR / f"{ts}-{slug}.md"
    path.write_text(skill_text, encoding="utf-8")
    return str(path)


# ══════════════════════════════════════════════════════════════════════════════
#  Skill Index — semantic retrieval via sentence-transformers
# ══════════════════════════════════════════════════════════════════════════════
import numpy as np

class SkillIndex:
    """
    Builds and caches a semantic embedding index over ~/.kdev/skills/*.md.
    Rebuilt only when the skills directory mtime changes.
    """
    MODEL_NAME  = "all-MiniLM-L6-v2"
    INDEX_NPY   = KDEV_DIR / "skills.index.npy"
    INDEX_JSON  = KDEV_DIR / "skills.index.json"
    MTIME_FILE  = KDEV_DIR / "skills.index.mtime"

    def __init__(self):
        self._model  = None
        self._vecs   = None
        self._meta   = []
        self._mtime  = None
        self._load_or_build()

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.MODEL_NAME)
        return self._model

    def _skills_mtime(self) -> float:
        try:
            return SKILLS_DIR.stat().st_mtime
        except Exception:
            return 0.0

    def _cached_mtime(self) -> float:
        try:
            return float(self.MTIME_FILE.read_text().strip())
        except Exception:
            return -1.0

    def _build(self):
        import json as _json
        skill_files = sorted(SKILLS_DIR.rglob("*.md"), reverse=True)
        if not skill_files:
            self._vecs = np.zeros((0, 384), dtype=np.float32)
            self._meta = []
            return
        texts = []
        meta  = []
        for sf in skill_files:
            try:
                text = sf.read_text(encoding="utf-8")
            except Exception:
                continue
            title_m   = re.search(r"title:\s*(.+)", text) or re.search(r"name:\s*(.+)", text)
            tags_m    = re.search(r"tags:\s*(.+)", text)
            summary_m = re.search(r"summary:\s*(.+)", text) or re.search(r"description:\s*(.+)", text)
            label   = title_m.group(1).strip()   if title_m   else sf.stem
            summary = summary_m.group(1).strip() if summary_m else ""
            tags    = tags_m.group(1).strip()    if tags_m    else ""
            embed_text = " ".join(filter(None, [label, tags, summary]))
            texts.append(embed_text)
            meta.append({"path": str(sf), "text": text, "label": label, "summary": summary})
        if not texts:
            self._vecs = np.zeros((0, 384), dtype=np.float32)
            self._meta = []
            return
        model = self._get_model()
        vecs  = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        self._vecs = vecs.astype(np.float32)
        self._meta = meta
        np.save(str(self.INDEX_NPY), self._vecs)
        self.INDEX_JSON.write_text(_json.dumps(self._meta, ensure_ascii=False), encoding="utf-8")
        self.MTIME_FILE.write_text(str(self._skills_mtime()))

    def _load_or_build(self):
        import json as _json
        current_mtime = self._skills_mtime()
        if (self.INDEX_NPY.exists()
                and self.INDEX_JSON.exists()
                and self._cached_mtime() == current_mtime):
            try:
                self._vecs = np.load(str(self.INDEX_NPY))
                self._meta = _json.loads(self.INDEX_JSON.read_text(encoding="utf-8"))
                self._mtime = current_mtime
                return
            except Exception:
                pass
        self._build()
        self._mtime = current_mtime

    def refresh_if_stale(self):
        current_mtime = self._skills_mtime()
        if current_mtime != self._mtime:
            self._build()
            self._mtime = current_mtime

    def top_k(self, query: str, k: int = 3) -> list:
        """Return top-k skill metadata dicts sorted by cosine similarity."""
        self.refresh_if_stale()
        if self._vecs is None or len(self._vecs) == 0:
            return []
        model  = self._get_model()
        q_vec  = model.encode([query], normalize_embeddings=True,
                               show_progress_bar=False)[0].astype(np.float32)
        scores = self._vecs @ q_vec
        idx    = np.argsort(scores)[::-1][:k]
        return [dict(score=float(scores[i]), **self._meta[i]) for i in idx]


_skill_index = None

def _get_skill_index():
    global _skill_index
    if _skill_index is None:
        _skill_index = SkillIndex()
    return _skill_index


# ══════════════════════════════════════════════════════════════════════════════
#  Skill Loading — semantic retrieval (replaces keyword matcher)
# ══════════════════════════════════════════════════════════════════════════════
def load_relevant_skills(task: str, max_skills: int = 3) -> str:
    """
    Semantic search over skill docs using sentence-transformers cosine similarity.
    Returns a formatted string to append to the system prompt.
    """
    if not SKILLS_DIR.exists():
        return ""
    try:
        index   = _get_skill_index()
        results = index.top_k(task, k=max_skills)
    except Exception:
        return ""
    if not results:
        return ""
    parts = ["## Relevant skills from previous sessions\n"]
    for r in results:
        text    = r["text"]
        label   = r["label"]
        summary = r["summary"]
        body    = re.sub(r"^---.*?---\s*", "", text, flags=re.DOTALL).strip()
        parts.append(f"### {label}")
        if summary:
            parts.append(f"*{summary}*\n")
        parts.append(body[:600])
        parts.append("")
    return "\n".join(parts)

def list_skills() -> list[dict]:
    """Return metadata for all skill docs (for /skills command)."""
    results = []
    for sf in sorted(SKILLS_DIR.glob("*.md"), reverse=True):
        try:
            text    = sf.read_text(encoding="utf-8")
            title_m   = re.search(r"title:\s*(.+)", text)
            summary_m = re.search(r"summary:\s*(.+)", text)
            tags_m    = re.search(r"tags:\s*(.+)", text)
            results.append({
                "file":    sf.name,
                "title":   title_m.group(1).strip()   if title_m   else sf.stem,
                "summary": summary_m.group(1).strip() if summary_m else "",
                "tags":    tags_m.group(1).strip()    if tags_m    else "",
            })
        except Exception:
            pass
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  Session Compression  (/compress)
#
#  Knowledge distillation technique:
#    1. Feed the full session to the LLM as "teacher"
#    2. Ask it to produce a compressed "student" version — all signal, no noise
#    3. Save as a compressed snapshot
#    4. Offer to update .agent.md with key decisions
# ══════════════════════════════════════════════════════════════════════════════
async def compress_session(
    message_history: list,
    workspace: str,
    session_id: str,
) -> dict:
    """
    Distill the full session into a compact knowledge snapshot.
    Returns dict with keys: summary, memory_update, skills_extracted, file_path
    """
    from pydantic_ai.messages import (
        ModelRequest, ModelResponse, UserPromptPart, TextPart
    )

    # Build a clean transcript
    import re as _re2
    lines = []
    for msg in message_history:
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    lines.append(f"USER: {part.content}")
        elif isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart) and part.content:
                    # Strip think blocks from compression input — distill answers only
                    clean = _re2.sub(r"<think>.*?</think>", "", part.content, flags=_re2.DOTALL).strip()
                    if clean:
                        lines.append(f"ASSISTANT: {clean[:500]}")

    if not lines:
        return {"error": "No conversation to compress."}

    transcript = "\n\n".join(lines)
    # Cap at ~6000 chars to avoid token overload
    if len(transcript) > 6000:
        transcript = transcript[:3000] + "\n\n[...middle trimmed...]\n\n" + transcript[-3000:]

    prompt = f"""You are applying knowledge distillation to compress a coding session transcript.

Workspace: {workspace}
Session length: {len(message_history)} messages

TRANSCRIPT:
{transcript}

Produce a compressed session document with these exact sections:

## Session Summary
2-3 sentences. What was accomplished?

## Key Decisions
Bullet list. Important architectural/technical choices made.

## What Worked
Bullet list. Approaches and patterns that were effective.

## What to Remember
Bullet list. Facts the agent should remember in future sessions
(project structure, conventions, user preferences discovered).

## Memory Update
A short paragraph (max 5 sentences) suitable for appending to .agent.md.
This is the highest-signal extract — write it as permanent reference notes.

## Skills Crystallised
List any reusable skills discovered this session (one line each).
Format: `skill_name: brief description`

Be ruthlessly concise. Every word must earn its place.
This document replaces the raw session transcript."""

    result = await _bedrock_call(
        prompt,
        system="You are a technical knowledge distillation system. Extract maximum signal, discard all noise. Write in terse bullet points."
    )

    if not result:
        return {"error": "Compression failed — LLM returned empty response."}

    # Redact any leaked secrets before writing to disk
    result = _redact_secrets(result)

    # Save compressed snapshot
    ts       = datetime.now().strftime("%Y%m%d-%H%M")
    snap_dir = KDEV_DIR / "compressed"
    snap_dir.mkdir(exist_ok=True)
    snap_path = snap_dir / f"{ts}-{session_id[:8]}.md"
    snap_path.write_text(
        _redact_secrets(
            f"# Compressed Session — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"Workspace: {workspace}\n\n"
            + result
        ),
        encoding="utf-8",
    )

    # Extract memory update section
    memory_update = ""
    mu_match = re.search(r"## Memory Update\n(.*?)(?=\n## |\Z)", result, re.DOTALL)
    if mu_match:
        memory_update = mu_match.group(1).strip()

    return {
        "summary":       result,
        "memory_update": memory_update,
        "file_path":     str(snap_path),
    }

# ══════════════════════════════════════════════════════════════════════════════
#  Self-Debugging — auto-diagnose unknown exceptions
# ══════════════════════════════════════════════════════════════════════════════
async def self_debug_error(
    error: Exception,
    traceback_str: str,
    user_task: str,
    message_history: list,
) -> str:
    """
    When kdev hits an unknown exception, call the LLM to diagnose it.
    Returns a markdown string with plain-English diagnosis and recovery steps.
    """
    from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart, TextPart
    import re as _re

    # Build compact recent history (last 3 exchanges max)
    recent = []
    exchanges = 0
    for msg in reversed(message_history):
        if exchanges >= 3:
            break
        if isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    recent.insert(0, f"USER: {part.content[:200]}")
                    exchanges += 1
        elif isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart) and part.content:
                    clean = _re.sub(r"<think>.*?</think>", "", part.content, flags=_re.DOTALL).strip()
                    recent.insert(0, f"ASSISTANT: {clean[:200]}")

    history_ctx = "\n".join(recent) if recent else "No recent history."
    tb_capped = traceback_str[-1500:] if len(traceback_str) > 1500 else traceback_str

    prompt = f"""You are kdev's self-debugging system. An unhandled exception just interrupted an agent task.

TASK THE USER GAVE:
{user_task[:300]}

RECENT CONVERSATION:
{history_ctx}

EXCEPTION:
{type(error).__name__}: {error}

TRACEBACK:
{tb_capped}

Diagnose this error concisely. Respond in this exact format:

## What went wrong
One sentence, plain English.

## Why
One or two sentences on the root cause.

## Fix
Exact action to take — be specific.

## Recovery
One of: "Retry the same prompt" / "Use /clear then retry" / "Restart kdev" / "Fix required first"

Be terse. No padding."""

    result = await _bedrock_call(
        prompt,
        system="You are a concise technical debugger. Diagnose errors in 4 sections. No preamble."
    )
    return result
