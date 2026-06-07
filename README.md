# kdev

> Local AI dev agent. Forged on a headless Linux server. Zero telemetry. No subscriptions.

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A self-hosted autonomous coding agent running on local LLMs via Ollama. Give it a task in plain
English — it reasons through a ReAct loop, writes code, reads files, runs shell commands, and
remembers what it learned. Built and iterated over three months on a headless Ubuntu server.

**Current state:** Core REPL, web UI, and skills system are stable and in daily use.
The autonomous scheduling subsystem — **Warden** + **Nocturne** — hit an architectural wall
and is under active investigation ([Issue #1](../../issues/1)).

---

## Architecture
kdev.py                      ←  REPL entry point
kdev_web.py                  ←  Web UI  (Flask · ReAct trace visualizer)
kdev_terminal_ui_v2.2.py     ←  Terminal UI  (Rich · live streaming)
kdev_tools.py                ←  Tool registry: file I/O, shell exec, memory ops
kdev_memory.py               ←  Session + workspace memory
skills.py                    ←  Self-learning loop
──────────────────────────────────────────────────────────────────────────
kdev_kairos_daemon.py        ←  Warden   — background execution scheduler  [experimental]
kdev_auto_dream.py           ←  Nocturne — autonomous self-improvement      [paused]
kdev_evolution_parser.py     ←  Evolution proposal engine                   [experimental]
kdev_autopilot.py            ←  Unattended execution mode                   [experimental]
──────────────────────────────────────────────────────────────────────────
kdev-skills/                 ←  Learned skill documents  (auto-generated per session)
agent-memory/                ←  Persistent agent memory
archive/                     ←  Historical iterations

**Warden** (`kdev_kairos_daemon.py`) schedules autonomous task runs on a configurable interval.
**Nocturne** (`kdev_auto_dream.py`) runs inside those slots — proposes, evaluates, and applies
self-improvements to the codebase. Currently paused pending architectural fixes to the loop.

---

## Install

```bash
git clone https://github.com/Yanflare/kdev-deploy
cd kdev-deploy
bash install.sh

cp .env.template .env
nano .env        # set OLLAMA_BASE_URL and OLLAMA_MODEL

source ~/.bashrc
kdev
```

**Requirements:** Python 3.12+, [Ollama](https://ollama.com/) running locally,
model pulled (e.g. `ollama pull qwen3:27b`).

---

## Run

```bash
kdev                              # interactive REPL
kdev "write tests for module X"   # single-shot
python3 kdev_web.py               # web UI  →  http://localhost:5000
python3 kdev_terminal_ui_v2.2.py  # terminal UI (Rich)
```

---

## Backends

Set in `.env` or switch live inside the REPL via `/backend <name>`:

| Backend | Key env var | Runtime command |
|---------|-------------|-----------------|
| Ollama (default) | `OLLAMA_BASE_URL` + `OLLAMA_MODEL` | `/backend ollama:qwen3:27b` |
| Anthropic | `ANTHROPIC_API_KEY` | `/backend anthropic` |
| AWS Bedrock | `AWS_BEARER_TOKEN_BEDROCK` | `/backend bedrock` |

---

## REPL Commands

| Command | What it does |
|---------|-------------|
| `/help` | Show all commands |
| `/clear` | Clear conversation history |
| `/memory` | Open workspace memory in editor |
| `/sessions` | List saved sessions |
| `/skills` | List learned skill documents |
| `/compress` | Distill current session into snapshot |
| `/backend <name>` | Switch LLM backend at runtime |

---

## Self-Learning

After any task involving ≥ 4 tool calls or ≥ 3 LLM rounds, kdev asks the model to distill
what it learned into a Markdown skill document saved at `~/.kdev/skills/`. On the next run,
relevant skills are keyword-matched and injected into the system prompt. No manual curation —
it compounds session over session.

Use `/compress` at the end of a session to save a compact knowledge snapshot.
Use `/skills` to inspect what's been accumulated.

---

## Contributing

Issues and PRs welcome. Active areas of interest:

- Warden/Nocturne loop reliability (see [Issue #1](../../issues/1))
- Memory pruning strategies for long-running agents
- Additional LLM backend support

---

## License

MIT — see [LICENSE](LICENSE).
