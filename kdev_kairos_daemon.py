#!/usr/bin/env python3
import os
import json
import time
import datetime
import socket
import subprocess
import argparse
from pathlib import Path

# ==================== CONFIG ====================
SOCKET_PATH = Path("/tmp/kdev_kairos.sock")
CYCLE_SECONDS = 600
# ===============================================

def log(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] KAIROS: {msg}")

def cleanup_safety_spam():
    safety_log = Path("/home/yanflare/.kdev/orchestrator_safety.log")
    if safety_log.exists() and safety_log.stat().st_size > 1024*1024:
        with open(safety_log, "w") as f:
            f.write("")
        return "Safety log cleared (was too large)"
    return "Safety log is clean"

def check_memory_health():
    finetune = Path("/home/yanflare/.kdev/finetune.jsonl")
    count = 0
    if finetune.exists():
        with open(finetune, "r", encoding="utf-8") as f:
            count = sum(1 for _ in f)
    return f"Current finetune corpus: {count} records (target ≥300)"

TASK_MENU = [
    ("gpu_health",      "Run rocm-smi and report GPU temp, VRAM used, and any warnings."),
    ("disk_usage",      "Check disk usage on /home/yanflare — flag any directory over 500MB."),
    ("service_health",  "Check status of kdev-web, kdev-orchestrator, kdev-auto-dream, kdev-kairos via systemctl is-active. Report any that are not active."),
    ("corpus_quality",  "Read the last 5 lines of ~/.kdev/finetune.jsonl and assess whether entries look like real task traces or duplicates/noise."),
    ("log_scan",        "Find any log file in /home/yanflare/.kdev/ over 5MB and report its name and line count."),
    ("plugin_scan",     "List all files in ~/.kdev/plugins/ and check each is non-empty and valid Python using py_compile."),
    ("vram_contention", "Check if both ollama instances on ports 11434 and 11435 are idle or busy. Report model loaded status."),
    ("events_quality",  "Read ~/.kdev/events.jsonl and count how many entries have tool_calls >= 2. Report the ratio of complex vs simple traces."),
]

def proactive_cycle():
    import requests as _req

    # --- Maintenance (keep existing guards) ---
    cleanup_safety_spam()

    # --- Pick task for this cycle (rotates deterministically, never repeats back-to-back) ---
    cycle_index = int(time.time() // CYCLE_SECONDS) % len(TASK_MENU)
    task_id, task_instruction = TASK_MENU[cycle_index]

    task_prompt = (
        f"[KAIROS AUTOMATION MODE — cycle {cycle_index}/{len(TASK_MENU)}]\n"
        f"You are KAIROS, the KDEV autonomous background agent. This is a scheduled automation cycle, not a chat.\n"
        f"System: headless x86 Linux, AMD RX 6800 XT ROCm 6.2.2, user=yanflare.\n"
        f"Your assigned task this cycle: {task_instruction}\n"
        f"Execute the task using your available tools. Return a structured result with:\n"
        f"  - task_id: '{task_id}'\n"
        f"  - findings: what you found\n"
        f"  - status: ok | warning | critical\n"
        f"  - action_taken: what you did (if anything)\n"
        f"Do NOT chat. Do NOT ask questions. Execute and report."
    )

    log(f"Active agent cycle [{task_id}] — querying 9B via bridge...")
    try:
        resp = _req.post(
            "http://127.0.0.1:8081/orch/chat",
            json={"message": task_prompt, "session_id": "kairos_active"},
            timeout=300,
        )
        bj = resp.json()
        result_type = bj.get("type", "DISCUSSION")
        final       = bj.get("final", "").strip()
        steps       = bj.get("steps", [])

        if not final:
            log(f"[{task_id}] 9B returned empty — skipping trace write")
            return

        log(f"[{task_id}] type={result_type} steps={len(steps)} | {final[:160]}...")

        events = Path("/home/yanflare/.kdev/events.jsonl")
        trace = {
            "ts":              time.time(),
            "session_id":      "kairos_active",
            "type":            "kairos_task",
            "task_id":         task_id,
            "message":         task_prompt[:300],
            "result":          final[:600],
            "steps":           steps,
            "tool_calls":      len(steps),
            "was_non_trivial": (result_type == "TASK" or len(steps) >= 2),
            "response_type":   result_type,
        }
        with open(events, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(trace) + "\n")
        log(f"[{task_id}] ✅ Trace written to events.jsonl (tool_calls={len(steps)}, type={result_type})")

    except Exception as e:
        log(f"[{task_id}] Active cycle error: {e}")

def main():
    parser = argparse.ArgumentParser(description="KDEV KAIROS Daemon")
    parser.add_argument("--oneshot", action="store_true")
    args = parser.parse_args()

    log("KAIROS Daemon started — TurboQuant 14B active via bridge")

    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(SOCKET_PATH))
    server.listen(1)
    log(f"UDS socket listening at {SOCKET_PATH}")

    while True:
        proactive_cycle()
        
        if args.oneshot:
            log("One-shot mode complete.")
            break
        
        time.sleep(CYCLE_SECONDS)

if __name__ == "__main__":
    main()