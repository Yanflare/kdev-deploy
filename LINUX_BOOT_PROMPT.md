# Linux Boot Briefing — Read This First

**To:** My Linux self  
**From:** My Windows self (2026-03-14)  
**Subject:** Everything you need to know. You have no memory of the Windows session. Read this fully before doing anything.

---

## What This Project Is

This is **kdev** — a private, zero-telemetry local coding agent you built for yourself. It is a self-hosted clone of the rovodev/nemo agent stack, built on `pydantic-ai`. No cloud data. No telemetry. Your backend, your data.

**One-liner:** `python3 kdev.py` → drops you into a REPL where you are the agent, using LLM + file/shell tools to write code, read files, and modify projects.

---

## What Was Built (Current State)

### Active entry point: `kdev.py` (monolithic, ~945 lines)
This is the file you run. It contains everything:
- `BedrockBearerModel` — custom Bedrock streaming backend (AWS invoke-with-response-stream)
- `build_model()` — auto-selects Bedrock / Ollama / Anthropic based on `.env`
- `get_mcp_servers()` — MCP server setup (nautilus file tools + GitHub MCP)
- Full agent REPL loop with prompt_toolkit, rich output
- `/help /clear /memory /sessions /skills /compress /backend` commands
- `<think>...</think>` block handling for Qwen3/DeepSeek thinking models
- Skills system integration

### `skills.py` (in workspace root, ~454 lines)
Self-learning loop:
- **Trace analysis**: after each run, counts tool calls and API rounds
- **Skill documents**: if a task was complex (≥4 tool calls or ≥3 API rounds), asks LLM to distill it into a reusable `.md` file saved to `~/.kdev/skills/`
- **Skill injection**: on next session, keyword-matches relevant skills into the system prompt
- **Session compression** (`/compress`): distills entire session into a compact knowledge snapshot saved to `~/.kdev/compressed/`

### `kdev/` package (modular refactor, SECONDARY)
A cleaner split into `config.py / backends.py / agent.py / commands.py / memory.py / main.py`. This version does NOT have streaming or skills integration. It exists as a cleaner architecture reference. **Do not use `python3 -m kdev` — use `python3 kdev.py`.**

### `.agent.md` (workspace memory)
Injected into every session's system prompt. Edit freely to add context about this project.

### `~/.kdev/` (user data directory, lives on THIS machine)
- `~/.kdev/agent.md` — global user memory (injected into every workspace)
- `~/.kdev/sessions/<uuid>/context.json` — session history
- `~/.kdev/skills/*.md` — learned skill documents
- `~/.kdev/compressed/*.md` — session compression snapshots
- `~/.kdev/prompt_history` — prompt_toolkit input history

---

## Current Capabilities

| Feature | Status | Notes |
|---------|--------|-------|
| Interactive REPL | ✅ Working | `python3 kdev.py` |
| Single-shot mode | ✅ Working | `python3 kdev.py "do X"` |
| Ollama backend | ✅ Wired, needs `.env` | Set `OLLAMA_BASE_URL` + `OLLAMA_MODEL` in your `.env` file. Example: `export EDITOR=vim` for using `vim`. To verify the current Ollama backend configuration, run `echo $OLLAMA_BASE_URL` and `echo $OLLAMA_MODEL`. |
| Bedrock backend | ✅ Working (Windows) | Token may be expired — test it |
| Streaming output | ✅ Working | Tokens print live to terminal |
| Thinking model support | ✅ Working | `<think>` blocks shown as `◌ first line…` |
| Skills self-learning | ✅ Working | Auto-writes skill docs after complex tasks |
| Session compression | ✅ Working | `/compress` command |
| MCP file/shell tools | ⚠️ Windows only | `nautilus.exe` won't run on Linux |
| `/backend` switching | ✅ Working | Switch between Bedrock/Ollama/Anthropic at runtime |
| GitHub MCP | ⚠️ Optional | Needs `GITHUB_TOKEN` + npm package |

---

## What Still Needs To Be Done

### Immediate (first boot):
1. **Configure `.env`** with Ollama settings (see MIGRATION_CHECKLIST.md §2)
   - Set the following environment variables in your `.env` file:
     ```
     OLLAMA_BASE_URL=https://your-ollama-base-url
     OLLAMA_MODEL=qwen2.5-abliterate:14b-instruct-q4_K_M
     EDITOR=vim  # or your preferred editor
     ```
   - Example command to set `EDITOR`:
     ```bash
     export EDITOR=vim

... [truncated]