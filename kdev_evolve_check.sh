#!/bin/bash
LAST_ACTIVITY_FILE="$HOME/.kdev/last_activity"
EVOLVE_LOG="$HOME/.kdev/evolve-cron.log"
IDLE_THRESHOLD=600
COOLDOWN=7200

if [ ! -f "$LAST_ACTIVITY_FILE" ]; then
    echo "[evolve-check] No last_activity file found, skipping" >> "$EVOLVE_LOG"
    exit 0
fi

LAST=$(cat "$LAST_ACTIVITY_FILE")
NOW=$(date +%s)
IDLE=$((NOW - LAST))

if [ "$IDLE" -lt "$IDLE_THRESHOLD" ]; then
    echo "[evolve-check] User active (idle ${IDLE}s), skipping" >> "$EVOLVE_LOG"
    exit 0
fi

LAST_EVOLVE=$(date -r "$EVOLVE_LOG" +%s 2>/dev/null || echo 0)
SINCE_EVOLVE=$((NOW - LAST_EVOLVE))
if [ "$SINCE_EVOLVE" -lt "$COOLDOWN" ]; then
    echo "[evolve-check] Cooldown active (${SINCE_EVOLVE}s < ${COOLDOWN}s), skipping" >> "$EVOLVE_LOG"
    exit 0
fi
echo "[evolve-check] Idle ${IDLE}s >= ${IDLE_THRESHOLD}s -- triggering evolve" >> "$EVOLVE_LOG"
cd /home/yanflare/kdev-deploy
/home/yanflare/.kdev-venv/bin/python3 kdev_evolve.py >> "$EVOLVE_LOG" 2>&1
