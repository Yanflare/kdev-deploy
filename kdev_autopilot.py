#!/usr/bin/env python3
"""
kdev_autopilot.py — KDEV Inactivity-Driven Autopilot Daemon
=============================================================
Runs as a systemd service (kdev-autopilot.service).
Polls last_activity every 60s. When user has been idle >= 10 minutes
AND evolve has not run in the last 6 hours, fires the act->reflect->
queue->improve->assess loop. Exits the loop the moment user activity
is detected. Holds a lock file to prevent concurrent runs.

Loop steps:
  1. Reflect  — scan events.jsonl for high-hop runs, update reflect-queue.txt
  2. Queue    — read top topic from reflect-queue.txt (if any)
  3. Evolve   — run kdev_evolve.py (with --hint if topic available)
  4. Assess   — check if recently written skills have been retrieved;
                if not, re-queue them as revision candidates
  5. Sleep 60s, recheck inactivity, loop or exit
"""

import os
import sys
import time
import json
import signal
import logging
import subprocess

# ── Config ────────────────────────────────────────────────────────────────────

KDEV_DIR            = "/home/yanflare/.kdev"
DEPLOY_DIR          = "/home/yanflare/kdev-deploy"
VENV_PYTHON         = "/home/yanflare/.kdev-venv/bin/python3"

LAST_ACTIVITY_FILE  = os.path.join(KDEV_DIR, "last_activity")
LOCK_FILE           = os.path.join(KDEV_DIR, "autopilot.lock")
REFLECT_QUEUE_FILE  = os.path.join(KDEV_DIR, "reflect-queue.txt")
EVENTS_LOG          = os.path.join(KDEV_DIR, "events.jsonl")
EVOLVE_LOG          = os.path.join(KDEV_DIR, "evolve-cron.log")
SKILLS_INDEX_JSON   = os.path.join(KDEV_DIR, "skills.index.json")
AUTOPILOT_LOG       = os.path.join(KDEV_DIR, "autopilot.log")

EVOLVE_SCRIPT       = os.path.join(DEPLOY_DIR, "kdev_evolve.py")

INACTIVITY_THRESHOLD  = 600    # seconds — 10 minutes
EVOLVE_COOLDOWN       = 7200   # seconds — 2 hours
AUTOPILOT_POLL        = 60     # seconds between idle checks
HOP_THRESHOLD         = 10     # hops >= this → candidate for reflect queue

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    filename=AUTOPILOT_LOG,
    level=logging.INFO,
    format="%(asctime)s [autopilot] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

def log(msg):
    logging.info(msg)
    print("[autopilot] " + msg, flush=True)

# ── Shutdown handling ─────────────────────────────────────────────────────────

_shutdown = False

def _handle_signal(signum, frame):
    global _shutdown
    log("Signal received — shutting down cleanly.")
    _shutdown = True

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

# ── Lock file ─────────────────────────────────────────────────────────────────

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            # Check if that PID is still alive
            os.kill(pid, 0)
            log("Lock held by PID " + str(pid) + " — another instance running. Exiting.")
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            # Stale lock — remove it
            log("Stale lock file found — removing.")
            os.remove(LOCK_FILE)
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True

def release_lock():
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
        except Exception:
            pass

# ── Inactivity check ──────────────────────────────────────────────────────────

def seconds_idle():
    """Return seconds since last_activity was written. Returns 0 if file missing."""
    if not os.path.exists(LAST_ACTIVITY_FILE):
        return 0
    try:
        with open(LAST_ACTIVITY_FILE, "r") as f:
            last = int(f.read().strip())
        return max(0, int(time.time()) - last)
    except Exception:
        return 0

def evolve_cooldown_ok():
    """True if evolve has NOT run in the last EVOLVE_COOLDOWN seconds."""
    if not os.path.exists(EVOLVE_LOG):
        return True
    try:
        mtime = os.path.getmtime(EVOLVE_LOG)
        return (time.time() - mtime) >= EVOLVE_COOLDOWN
    except Exception:
        return True

def user_active():
    """True if user has been active within INACTIVITY_THRESHOLD."""
    return seconds_idle() < INACTIVITY_THRESHOLD

# ── Step 1: Reflect ───────────────────────────────────────────────────────────

def run_reflect_step():
    """Delegate to kdev_evolve.py --reflect-queue."""
    log("Step 1: Reflect — updating reflect-queue.txt")
    try:
        result = subprocess.run(
            [VENV_PYTHON, EVOLVE_SCRIPT, "--reflect-queue"],
            capture_output=True, text=True, timeout=60
        )
        if result.stdout.strip():
            for line in result.stdout.strip().splitlines():
                log("  evolve: " + line)
        if result.returncode != 0:
            log("  reflect step exited with code " + str(result.returncode))
    except subprocess.TimeoutExpired:
        log("  reflect step timed out")
    except Exception as e:
        log("  reflect step error: " + str(e))

# ── Step 2: Queue — read top topic ───────────────────────────────────────────

def pop_top_topic():
    """
    Read the first line of reflect-queue.txt as the hint topic.
    Does NOT remove it — topics stay until they are actioned by evolve
    and assessed as retrieved. Returns empty string if queue is empty.
    """
    if not os.path.exists(REFLECT_QUEUE_FILE):
        return ""
    try:
        with open(REFLECT_QUEUE_FILE, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        return lines[0] if lines else ""
    except Exception:
        return ""

# ── Step 3: Evolve ────────────────────────────────────────────────────────────

def run_evolve_step(hint=""):
    """Run kdev_evolve.py, optionally with --hint. Returns True if successful."""
    cmd = [VENV_PYTHON, EVOLVE_SCRIPT]
    if hint:
        cmd += ["--hint", hint]
        log("Step 3: Evolve — hint: " + hint[:80])
    else:
        log("Step 3: Evolve — no hint, free planning")

    evolve_env = os.environ.copy()
    try:
        with open(EVOLVE_LOG, "a") as logf:
            result = subprocess.run(
                cmd,
                stdout=logf,
                stderr=logf,
                timeout=900,   # 15 minute hard cap
                env=evolve_env,
            )
        if result.returncode == 0:
            log("Step 3: Evolve completed OK")
            return True
        else:
            log("Step 3: Evolve exited with code " + str(result.returncode))
            return False
    except subprocess.TimeoutExpired:
        log("Step 3: Evolve timed out (>15min) — killed")
        return False
    except Exception as e:
        log("Step 3: Evolve error: " + str(e))
        return False

# ── Step 4: Assess ────────────────────────────────────────────────────────────

def run_assess_step():
    """
    Check skills written in the last 3 evolve sessions against skills.index.json.
    Skills with retrieval_count == 0 after appearing in >= 3 sessions are
    re-queued as revision candidates.

    skills.index.json format (from skills.py): list of dicts with keys:
      path, title, mtime, retrieval_count (if present)
    """
    log("Step 4: Assess — checking skill retrieval rates")
    if not os.path.exists(SKILLS_INDEX_JSON):
        log("  skills.index.json not found — skipping assess")
        return

    try:
        with open(SKILLS_INDEX_JSON, "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception as e:
        log("  Could not read skills.index.json: " + str(e))
        return

    now = time.time()
    three_sessions_ago = now - (EVOLVE_COOLDOWN * 3)  # ~18 hours

    zero_retrieval = []
    for entry in index:
        if not isinstance(entry, dict):
            continue
        mtime = entry.get("mtime", 0)
        retrieval_count = entry.get("retrieval_count", None)
        path = entry.get("path", "")
        title = entry.get("title", os.path.basename(path))

        # Only assess skills written in the last 3+ evolve windows
        if mtime > three_sessions_ago:
            continue
        # Only flag skills that have a retrieval_count field and it is 0
        if retrieval_count is None:
            continue
        if retrieval_count == 0:
            zero_retrieval.append(title)

    if not zero_retrieval:
        log("  Assess: all recent skills have been retrieved at least once")
        return

    # Re-queue as revision candidates
    existing = set()
    if os.path.exists(REFLECT_QUEUE_FILE):
        with open(REFLECT_QUEUE_FILE, "r", encoding="utf-8") as f:
            existing = set(l.strip() for l in f if l.strip())

    added = 0
    with open(REFLECT_QUEUE_FILE, "a", encoding="utf-8") as f:
        for title in zero_retrieval:
            candidate = "Revise skill (0 retrievals): " + title
            if candidate not in existing:
                f.write(candidate + chr(10))
                added += 1

    log("  Assess: re-queued " + str(added) + " zero-retrieval skill(s) for revision")

# ── Main loop ─────────────────────────────────────────────────────────────────

def autopilot_loop():
    """One full act->reflect->queue->improve->assess cycle."""
    log("=== Autopilot loop starting ===")

    # Step 1: Reflect
    run_reflect_step()
    if user_active() or _shutdown:
        log("User active after reflect — aborting loop")
        return

    # Step 2: Queue
    hint = pop_top_topic()
    if hint:
        log("Step 2: Queue — top topic: " + hint[:80])
    else:
        log("Step 2: Queue — reflect-queue.txt empty, free evolve run")

    if user_active() or _shutdown:
        log("User active after queue — aborting loop")
        return

    # Step 3: Evolve
    run_evolve_step(hint=hint)
    if user_active() or _shutdown:
        log("User active after evolve — aborting loop")
        return

    # Step 4: Assess
    run_assess_step()

    log("=== Autopilot loop complete ===")

def main():
    log("Autopilot daemon starting (PID " + str(os.getpid()) + ")")

    if not acquire_lock():
        sys.exit(1)

    try:
        in_autopilot = False

        while not _shutdown:
            idle = seconds_idle()
            cooldown_ok = evolve_cooldown_ok()

            if idle >= INACTIVITY_THRESHOLD and cooldown_ok:
                if not in_autopilot:
                    log("Idle " + str(idle) + "s >= " + str(INACTIVITY_THRESHOLD) +
                        "s and evolve cooldown clear — entering autopilot")
                    in_autopilot = True
                autopilot_loop()
                in_autopilot = not user_active()
            else:
                if in_autopilot:
                    log("User active — exiting autopilot mode")
                    in_autopilot = False

            # Sleep in 5s increments so we can react to signals promptly
            for _ in range(AUTOPILOT_POLL // 5):
                if _shutdown:
                    break
                time.sleep(5)

    finally:
        release_lock()
        log("Autopilot daemon stopped.")

if __name__ == "__main__":
    main()
