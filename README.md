# kdev — Private Coding Agent

A self-hosted, zero-telemetry local coding agent built on `pydantic-ai`. Your backend, your data. No cloud logging, no rate limits, no subscription.

Drop into a REPL, give it tasks in plain English, and it uses LLM + file/shell tools to write code, read files, and modify projects. It learns from its own sessions and gets better over time.

---

## What's in this package

```
kdev-deploy/
├── kdev.py                  ← Main entry point (run this)
├── skills.py                ← Self-learning loop (must be alongside kdev.py)
├── requirements.txt         ← Pinned Python dependencies
├── .env.template            ← Config template — copy to .env and fill in
├── install.sh               ← One-shot setup script for Linux
├── README.md                ← This file
├── LINUX_BOOT_PROMPT.md     ← Full architecture briefing for first boot
├── MIGRATION_CHECKLIST.md   ← File-by-file migration notes (Windows → Linux)
├── kdev-skills/             ← Learned skill documents from previous sessions
│   ├── 20260313-*.md
│   └── ...
└── agent-memory/            ← Persistent memory files
    ├── user-agent.md        ← Global user memory (placed at ~/.kdev/agent.md)
    └── workspace-agent.md   ← Workspace memory (placed at ./.agent.md)
```

---

## Quick Install (Linux)

```bash
# 1. Clone or SCP this folder onto your machine, then:
cd kdev-deploy
bash install.sh

# 2. Edit your config
nano .env
# Set: OLLAMA_BASE_URL=http://localhost:11434
#      OLLAMA_MODEL=qwen3:27b

# 3. Reload shell and launch
source ~/.bashrc
kdev
```

That's it. The install script handles everything else.

---

## Manual Install (if you prefer)

```bash
# Create venv
python3 -m venv ~/.kdev-venv
~/.kdev-venv/bin/pip install -r requirements.txt

# Create data dirs
mkdir -p ~/.kdev/{sessions,skills,compressed}

# Copy skills
cp kdev-skills/*.md ~/.kdev/skills/

# Set up config
cp .env.template .env
nano .env

# Run directly
~/.kdev-venv/bin/python kdev.py
```

---

## Launching kdev

After install, the `kdev` alias is registered in `~/.bashrc`:

```bash
source ~/.bashrc          # load the alias (only needed once per shell session)

kdev                      # interactive REPL
kdev "do something"       # single-shot mode (run one task and exit)
```

Or run directly without the alias:

```bash
~/.kdev-venv/bin/python /path/to/kdev.py
```

---

## REPL Commands

Once inside the interactive REPL, these slash commands are available:

| Command | What it does |
|---------|-------------|
| `/help` | Show all available commands |
| `/clear` | Clear conversation history (start fresh) |
| `/memory` | Open the workspace memory file in your editor |
| `/sessions` | List saved sessions |
| `/skills` | List learned skill documents |
| `/compress` | Distill current session into a compressed knowledge snapshot |
| `/backend <name>` | Switch LLM backend at runtime (see below) |
| `exit` or `Ctrl+D` | Quit kdev |

---

## Switching Backends

kdev supports three backends, switchable at runtime via `/backend` or by editing `.env`:

### Ollama (recommended for Linux)
```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:27b
```
Inside REPL: `/backend ollama:qwen3:27b`

### AWS Bedrock (requires Atlassian SSO bearer token)
```env
AWS_BEARER_TOKEN_BEDROCK=<token>
AWS_REGION=us-east-1
```
Inside REPL: `/backend bedrock`

### Direct Anthropic API
```env
ANTHROPIC_API_KEY=sk-ant-...
```
Inside REPL: `/backend anthropic`

---

## How the Self-Learning Works

After every complex task (≥4 tool calls or ≥3 API rounds), kdev asks the LLM to distill what it learned into a **skill document** saved at `~/.kdev/skills/`. On the next session, relevant skills are keyword-matched and injected into the system prompt — the agent gets better over time without any manual curation.

Use `/compress` at end of session to save a compact knowledge snapshot. Use `/skills` to see what's been learned.

---

## File Locations

| Path | Purpose |
|------|---------|
| `kdev.py` | Main entry point — run this |
| `skills.py` | Self-learning module — must be alongside `kdev.py` |
| `.env` | Backend config (git-ignored) |
| `.agent.md` | Workspace-level memory injected into every session |
| `~/.kdev/agent.md` | Global user memory injected into every session |
| `~/.kdev/sessions/` | Saved session history (JSON) |
| `~/.kdev/skills/` | Learned skill documents (Markdown) |
| `~/.kdev/compressed/` | Session compression snapshots |
| `~/.kdev/prompt_history` | Input history for up-arrow recall |

---

## Known Issues on Fresh Linux Install

1. **MCP tools unavailable** — `nautilus.exe` is a Windows binary. kdev prints a yellow warning and degrades gracefully. Core chat still works. See `MIGRATION_CHECKLIST.md §3` for Linux MCP alternatives.

2. **`/memory` command** — uses `os.startfile()` (Windows-only). Fix: replace with `subprocess.Popen([os.getenv("EDITOR","nano"), str(MEMORY_FILE)])` in `kdev.py` around line 633.

3. **Python 3.11+ required** — Ubuntu 22.04 ships Python 3.10. Use the deadsnakes PPA if needed:
   ```bash
   sudo add-apt-repository ppa:deadsnakes/ppa
   sudo apt install python3.11 python3.11-venv
   ```

4. **pydantic-ai version** — pinned to `1.67.0`. If you install a newer version and get `ImportError` on `ModelRequest`/`TextPart`, reinstall with the pinned version from `requirements.txt`.

---

## Architecture

```
kdev.py          ← Monolith. All features: streaming, skills, thinking model support.
skills.py        ← Self-learning. Imported by kdev.py. Must be co-located.
kdev/            ← Modular refactor (secondary). No streaming, no skills. Don't use.
.env             ← Backend config. Never commit this.
.agent.md        ← Workspace memory. Edit freely to add project context.
```

**Entry point is always `kdev.py`.** The `kdev/` package is an architectural experiment — it lacks streaming and the skills system. Don't run `python3 -m kdev`.

---

## First Boot Checklist

```bash
python3 --version                    # verify 3.11+
curl http://localhost:11434/api/tags  # verify Ollama is running
ollama list                           # verify qwen3:27b is pulled
cat .env                              # verify OLLAMA_* vars are set
kdev "hello, confirm you are on Linux with Ollama"  # smoke test
```

See `LINUX_BOOT_PROMPT.md` for the full briefing.
