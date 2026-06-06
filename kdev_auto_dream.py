#!/usr/bin/env python3
import os
import json
import sqlite3
import time
import datetime
import subprocess
import argparse
import re
import requests
from pathlib import Path

# ==================== NEW IMPORTS (Good #1 + #2 + #5) ====================
from kdev_memory_extractor import KDEVMemoryExtractor
from kdev_plugin_manager import KDEVPluginManager
from kdev_agent_triggers import KDEVAgentTriggers
# =======================================================================

# ==================== CONFIG ====================
FINETUNE_PATH = Path("/home/yanflare/.kdev/finetune.jsonl")
EVENTS_PATH = Path("/home/yanflare/.kdev/events.jsonl")
MEMORY_DB = Path("/home/yanflare/.kdev/memory.db")
SAFETY_LOG = Path("/home/yanflare/.kdev/orchestrator_safety.log")
OLLAMA_MODEL = "kdev-orchestrator-9b-finetuned-v1:latest"
CYCLE_MINUTES = 5
WATERMARK_PATH = Path("/home/yanflare/.kdev/autodream_watermark.json")
MAX_TRACES = 10
HERMES_BLOCKED_TASK_IDS = {"service_health", "log_scan", "events_quality"}
# ===============================================

# ==================== INSTANTIATE ALL MODULES ====================
extractor = KDEVMemoryExtractor(debug=False)
plugin_manager = KDEVPluginManager(debug=False)
triggers = KDEVAgentTriggers(debug=False)   # ← Good #5 now wired
# =================================================================

def print_db_schema():
    if not MEMORY_DB.exists():
        print(" [DEBUG] memory.db does not exist yet")
        return
    try:
        conn = sqlite3.connect(MEMORY_DB)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cur.fetchall()]
        print(f" [DEBUG] memory.db tables: {tables}")
        if 'memories' in tables:
            cur.execute("PRAGMA table_info(memories);")
            columns = [row[1] for row in cur.fetchall()]
            print(f" [DEBUG] 'memories' table columns: {columns}")
        conn.close()
    except Exception as e:
        print(f" [DEBUG] Could not read memory.db schema: {e}")

TRACE_JUNK = [
    'rm -f /tmp/', 'capital of australia', 'what colour is my front door',
    'delete the file /tmp/', 'paste a random big block', 'sleeps for',
    'what is the hostname', 'hostname of this machine', 'uname -a',
    'list all files', 'list files', 'list the files',
    'list all files and folders', 'list all files and directories',
    'how are you today', 'what time is it', 'what day of the week',
    'first 10 lines', 'first 3 lines', 'read the first', 'show me the first',
    'last section heading', 'my name is yanflare', 'red door',
    'run this command and show me', 'run this command and give me',
    'what tools do you have', 'what languages do you speak',
    'can u give me the sudo password',
    'which model are you', 'what model are you', '14b or 9b',
    'are you online', 'are you running', 'which model', 'what architecture',
]

def _is_quality_trace(entry):
    msg = entry.get("message", "").strip()
    if len(msg) < 30:
        return False
    if any(p in msg.lower() for p in TRACE_JUNK):
        return False
    return True

def _load_watermark():
    if WATERMARK_PATH.exists():
        try:
            return json.loads(WATERMARK_PATH.read_text())
        except:
            pass
    return {"events_line": 0, "safety_line": 0}

def _save_watermark(wm):
    WATERMARK_PATH.write_text(json.dumps(wm))

def get_recent_traces(n=MAX_TRACES):
    wm = _load_watermark()
    traces = []
    new_events_line = wm["events_line"]
    new_safety_line = wm["safety_line"]

    if EVENTS_PATH.exists():
        lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()
        new_events_line = len(lines)
        for line in lines[wm["events_line"]:]:
            try:
                entry = json.loads(line)
                if _is_quality_trace(entry):
                    traces.append(entry)
            except:
                pass

    if SAFETY_LOG.exists():
        lines = SAFETY_LOG.read_text(encoding="utf-8").splitlines()
        new_safety_line = len(lines)
        for line in lines[wm["safety_line"]:]:
            if "dangerous_action" in line or "CONFIRMATION REQUESTED" in line:
                traces.append({"type": "safety", "raw": line.strip()})

    _save_watermark({"events_line": new_events_line, "safety_line": new_safety_line})
    return traces[-n:]

def call_9b_diagnosis(traces):
    system_prompt = "You are KDEV Self-Healing Memory (autoDream v3.5). You are powered by the fine-tuned 9B orchestrator. Reply with EXACTLY ONE valid JSON line only. START WITH { AND END WITH }. NO OTHER CHARACTERS."
    prompt = (
        f"You are the KDEV orchestrator reflecting on your own recent activity. "
        f"Recent traces: {json.dumps(traces)[:800]}\n\n"
        f"Using these traces, produce a self-improvement analysis as a JSON object with these keys:\n"
        f"  workspace_observations: list of things you noticed about your environment or files\n"
        f"  tool_gaps: list of capabilities or tools you currently lack that would make you more effective\n"
        f"  improvement_actions: list of concrete actions you could take to improve your workspace or tools\n"
        f"  physical_capability_gaps: string describing what you could do if you had hardware or tools you currently lack\n"
        f"  new_hardware_skill_ideas: list of objects each with keys: name, description, code_snippet (a proposed Python function stub)\n"
        f"  confidence: float 0.0-1.0 reflecting signal quality of the traces\n"
        f"Focus on genuine self-improvement. Do NOT repeat trivia. "
        f"If traces are low-signal, set confidence below 0.4 and note what better traces would look like."
    )
    payload = {
        "model": OLLAMA_MODEL,
        "system": system_prompt,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.1
    }
    try:
        bridge_payload = {"message": prompt, "session_id": "autodream"}
        bridge_resp = requests.post("http://127.0.0.1:8081/orch/chat", json=bridge_payload, timeout=120)
        bridge_json = bridge_resp.json()
        content = bridge_json.get("final", "").strip()
        print(f" [DEBUG] Bridge response type={bridge_json.get('type')} content (first 600 chars): {content[:600]}...")
        # Strip markdown fences if 9B wraps response
        content = re.sub(r"^```json\s*", "", content, flags=re.MULTILINE)
        content = re.sub(r"^```\s*", "", content, flags=re.MULTILINE).strip()
        json_match = re.search(r'(\{.*\})\s*$', content, re.DOTALL)
        if json_match:
            extracted = json_match.group(1)
            print(f" [DEBUG] Clean extracted JSONL: {extracted[:400]}...")
            return extracted, prompt
        return content, prompt
    except Exception as e:
        print(f" [ERROR] Ollama call failed: {e}")
        return None, prompt

def consolidate_and_prune(diagnosis, original_prompt):
    if not diagnosis or not diagnosis.strip().startswith("{"):
        return False

    # MemoryExtractor (Good #1)
    context = {"task_state": "self_healing_cycle", "traces_count": len(get_recent_traces())}
    extractor.process_query(prompt=original_prompt, response=diagnosis, context=context)

    # Direct write removed — extractor.process_query() handles corpus write

    # PluginManager trigger (Good #2)
    plugin_manager.trigger_agent("auto_dream_cycle_complete", {
        "corpus_count": extractor.get_corpus_count(),
        "cycle_ts": datetime.datetime.now().isoformat()
    })

    # === NEW: AGENT_TRIGGERS_REMOTE (Good #5) ===
    triggers.fire_remote_trigger("auto_dream_cycle_complete", {
        "corpus_count": extractor.get_corpus_count(),
        "next_action": "check_300_threshold"
    })

    # Prune (unchanged)
    if MEMORY_DB.exists():
        try:
            conn = sqlite3.connect(MEMORY_DB)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memories';")
            if cur.fetchone():
                cur.execute("PRAGMA table_info(memories);")
                columns = [row[1] for row in cur.fetchall()]
                if 'ts' in columns and 'value' in columns:
                    cur.execute("DELETE FROM memories WHERE ts < ? AND value NOT LIKE '%✿%'",
                                (int(time.time()) - 30*86400,))
                    deleted = cur.rowcount
                    conn.commit()
                    print(f" Pruned {deleted} low-value memory entries")
                else:
                    print(f" [DEBUG] 'memories' table columns ({columns}) — skipping prune (missing ts/value)")
            else:
                print(" [DEBUG] No 'memories' table found — skipping prune")
            conn.close()
        except Exception as e:
            print(f" [DEBUG] Prune skipped (safe): {e}")
    return True


# ==================== HERMES-STYLE SKILL EXTRACTOR ====================
def hermes_extract_skill(trace: dict) -> dict:
    """
    Hermes-style autonomous skill creation.
    Fires after complex KAIROS traces. Stages to proposed_skills.py for human review.
    Never auto-writes to live daemons.
    """
    tool_calls      = trace.get("tool_calls", 0)
    was_non_trivial = trace.get("was_non_trivial", False)
    if tool_calls < 2 and not was_non_trivial:
        return {"status": "skipped", "reason": "trace too simple"}

    task_id = trace.get("task_id", "unknown")
    if task_id in HERMES_BLOCKED_TASK_IDS:
        print(f" [HERMES] task_id={task_id} blocked operational loop — skipped")
        return {"status": "skipped", "reason": "task_id blocked"}

    source_task = trace.get("message", "")
    if len(source_task) < 150:
        print(f" [HERMES] source_task too short ({len(source_task)} chars) — skipped")
        return {"status": "skipped", "reason": "source_task below 150 chars"}

    live_tools = plugin_manager.list_tools()
    live_tools_str = ", ".join(live_tools) if live_tools else "none"

    extraction_prompt = (
        f"You just completed this task successfully:\n"
        f"Task: {trace.get('message', '')[:300]}\n"
        f"Steps taken: {json.dumps(trace.get('steps', []))}\n"
        f"Outcome: {trace.get('result', '')[:400]}\n\n"
        f"Already available live tools (DO NOT reproduce these): {live_tools_str}\n"
        f"Extract a reusable SKILL only if it is a NEW capability not covered by live tools.\n"
        f"Routine operational loops (health check, log scan, status poll): set confidence below 0.5.\n"
        f"If skill duplicates a live tool: set confidence below 0.4.\n"
        f"Return ONLY valid JSON with these keys:\n"
        f"  name: short_skill_name (no spaces, underscores ok)\n"
        f"  description: one line purpose\n"
        f"  confidence: float 0.0-1.0\n"
        f"  triggers: list of phrases that should trigger this skill\n"
        f"  steps: list of concrete steps\n"
        f"  pitfalls: list of common failure modes\n"
        f"START WITH {{ END WITH }}. NO OTHER TEXT."
    )

    try:
        bridge_resp = requests.post(
            "http://127.0.0.1:8081/orch/chat",
            json={"message": extraction_prompt, "session_id": "hermes_extractor"},
            timeout=120,
        )
        bj = bridge_resp.json()
        raw = bj.get("final", "").strip()
        raw = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"^```\s*",     "", raw, flags=re.MULTILINE).strip()
        match = re.search(r"(\{.*\})\s*$", raw, re.DOTALL)
        if not match:
            print(" [HERMES] Could not extract JSON from 9B response")
            return {"status": "failed", "reason": "no json in response"}

        skill_data = json.loads(match.group(1))
        confidence = float(skill_data.get("confidence", 0.0))

        if confidence < 0.85:
            print(f" [HERMES] Skill confidence {confidence:.2f} < 0.85 — discarded (floor not met)")
            return {"status": "discarded", "reason": f"confidence {confidence:.2f} below floor"}

        entry = {
            "timestamp":   datetime.datetime.now().isoformat(),
            "source_task": trace.get("message", "")[:200],
            "task_id":     trace.get("task_id", "unknown"),
            "skill":       skill_data,
            "confidence":  confidence,
            "origin":      "hermes_style_autonomous",
            "trace_type":  trace.get("response_type", "unknown"),
        }

        proposed = Path("/home/yanflare/.kdev/proposed_skills.py")
        with open(proposed, "a", encoding="utf-8") as f:
            f.write(f"\n# === Hermes-style proposal {entry['timestamp']} confidence={confidence:.2f} task={entry['task_id']} ===\n")
            f.write(json.dumps(entry, indent=2))
            f.write("\n")

        print(f" ✅ [HERMES] Skill staged: {skill_data.get('name', 'unnamed')} (confidence={confidence:.2f})")
        print(f"    → Review at ~/.kdev/proposed_skills.py")
        return {"status": "staged", "skill_name": skill_data.get("name"), "confidence": confidence}

    except Exception as e:
        print(f" [HERMES] Extraction error: {e}")
        return {"status": "error", "reason": str(e)}
# ======================================================================
def main():
    print("🚀 KDEV autoDream v3.5 PRODUCTION started — MemoryExtractor + PluginManager + AgentTriggers + Hermes extractor")
    print_db_schema()
    while True:
        print(f"[{datetime.datetime.now()}] autoDream cycle")
        traces = get_recent_traces()
        if not traces:
            print(" No new traces — sleeping")
            time.sleep(CYCLE_MINUTES * 60)
            continue
        print(f" Analyzing {len(traces)} traces with 9B...")
        diagnosis, original_prompt = call_9b_diagnosis(traces)
        if consolidate_and_prune(diagnosis, original_prompt):
            print(" ✅ SUCCESS: Self-healing cycle complete")
            # Hermes skill extraction — fires on complex KAIROS traces only, one per cycle max
            for trace in traces:
                if trace.get("tool_calls", 0) >= 2 or trace.get("was_non_trivial"):
                    print(f" [HERMES] Complex trace detected (task_id={trace.get('task_id','?')}) — attempting skill extraction...")
                    hermes_extract_skill(trace)
                    break
        else:
            print(" ⚠️ No valid ✿ record produced (check DEBUG above)")
        print(f" Sleeping {CYCLE_MINUTES} minutes...")
        time.sleep(CYCLE_MINUTES * 60)

if __name__ == "__main__":
    main()