# KDEV Orchestrator Interface Contract
# Version: 1.0 (Phase 2D — 9B Orchestrator + Safety Layer)
# Last updated: 2026-03-31

## Models
- **Orchestrator:** huihui_ai/qwen3.5-abliterated:9b-Claude
  Runs on Ollama port 11435. Handles classification, decomposition, aggregation,
  and direct DISCUSSION responses.
- **Worker:** huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M
  Runs on Ollama port 11434 (primary instance, unchanged). Executes atomic tool tasks
  via kdev-web on port 8080.

## Bridge
- Listens on http://127.0.0.1:8081/orch/chat (POST, JSON)
- Request schema:  {"message": "...", "session_id": "..."}  (session_id optional)
- Response schema: {"type": "DISCUSSION"|"TASK", "final": "...", "steps": [...],
                    "step_results": [...], "session_id": "..."}

## Message Classification
Every incoming message is classified as DISCUSSION or TASK by the 9B orchestrator.
DISCUSSION: orchestrator responds directly. Worker (14b) is never invoked.
TASK: orchestrator decomposes → delegates each atomic step to worker → aggregates.

Classification trigger words (DISCUSSION if any present):
  hypothetically, theoretically, how would you, thought process, what would you,
  discuss, how do you, what do you think, how do you feel, evaluate this, reflect,
  tell me about yourself, brief you, your opinion, your thoughts, do you think,
  what is your

Prefix override: message starting with "DISCUSSION MODE" → always DISCUSSION.

## Delegation Format
Worker receives one atomic instruction per call:
  POST http://localhost:11434/api/chat
  {"model": "huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M",
   "messages": [{"role": "user", "content": "<ATOMIC INSTRUCTION>"}],
   "stream": false, "options": {"temperature": 0.2}}

Atomic instruction rules:
  - Single sentence, no newlines, no semicolons, max 200 characters.
  - Self-contained — no prior context assumed.

## Safety Layer (background thread, 30s poll)
Monitors /home/yanflare/.kdev/events.jsonl continuously.
Triggers:
  1. Same error ≥ 4 times in last 4 events → warning + Telegram alert
  2. Current task wall time > 480s → warning + Telegram alert
  3. Protected path targeted by destructive shell command → emergency_stop
     (stops kdev-autopilot, sends Telegram EMERGENCY alert)

Protected paths:
  /home/yanflare/kdev-deploy/kdev_web.py
  /home/yanflare/kdev-deploy/kdev_tools.py
  /home/yanflare/kdev-deploy/kdev_evolve.py
  /home/yanflare/kdev-deploy/kdev_autopilot.py
  /home/yanflare/.kdev/finetune.jsonl
  /home/yanflare/.kdev/memory.db

## Logs
  /home/yanflare/.kdev/orchestrator_safety.log  — safety events (JSON lines)
