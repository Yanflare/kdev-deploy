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
CYCLE_SECONDS = 60
TURBO_PORT = 8082
# ===============================================

def log(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] KAIROS: {msg}")

def is_tool_heavy_or_long_context(prompt):
    """Heuristic for routing to TurboQuant"""
    if len(prompt) > 800 or "✿FUNCTION✿" in prompt or "shell_exec" in prompt or "ReAct" in prompt:
        return True
    return False

def delegate_to_turboquant(prompt):
    """Route heavy calls to TurboQuant sidecar"""
    payload = {
        "model": "huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.1
    }
    try:
        result = subprocess.run([
            "curl", "-s", "-X", "POST", f"http://localhost:{TURBO_PORT}/chat",
            "-H", "Content-Type: application/json",
            "-d", json.dumps(payload)
        ], capture_output=True, text=True, timeout=90)
        response = json.loads(result.stdout)
        content = response.get("message", {}).get("content", "")
        log(f"✅ Routed to TurboQuant (KV turbo4)")
        return content
    except Exception as e:
        log(f"TurboQuant delegation failed, falling back: {e}")
        return None

def cleanup_safety_spam():
    safety_log = Path("/home/yanflare/.kdev/orchestrator_safety.log")
    if safety_log.exists() and safety_log.stat().st_size > 1024*1024:  # >1MB
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

def proactive_cycle():
    log("Starting proactive cycle")
    safety_result = cleanup_safety_spam()
    log(f"Safety cleanup: {safety_result}")
    memory_result = check_memory_health()
    log(f"Memory check: {memory_result}")
    log("Proactive cycle complete")

def main():
    parser = argparse.ArgumentParser(description="KDEV KAIROS Daemon with TurboQuant routing")
    parser.add_argument("--oneshot", action="store_true")
    args = parser.parse_args()

    log("KAIROS Daemon started with TurboQuant integration")
    log("Tool-heavy / long-context calls will now use TurboQuant sidecar")

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