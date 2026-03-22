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
| Ollama backend | ✅ Wired, needs `.env` | Set `OLLAMA_BASE_URL` + `OLLAMA_MODEL` |
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
2. **Verify Ollama** is running and `qwen2.5-abliterate:14b-instruct-q4_K_M` is pulled
3. **Fix `/memory` command** — `os.startfile()` is Windows-only, will crash on Linux
   - In `kdev.py` at the `/memory` handler (~line 633): replace `os.startfile(str(MEMORY_FILE))` with:
     ```python
     import subprocess
     subprocess.Popen([os.getenv("EDITOR", "nano"), str(MEMORY_FILE)])
     ```
   - Same fix needed in `kdev/commands.py` line ~95
4. **Plan Linux MCP solution** — nautilus.exe is a Windows binary, won't work. Options:
   - Check if Atlassian/rovodev releases a Linux binary at `~/.rovodev/...`
   - Use `@modelcontextprotocol/server-filesystem` via npx
   - Run without MCP (agent still works, just no file/shell tools via MCP — it can still use Python to do things)

### Medium-term:
- `/prune` command — delete old sessions
- `/load <n>` command — restore a previous session  
- Shell completion for REPL commands
- Linux MCP integration (the big one)

---

## Known Issues

1. **`os.startfile()` will crash on Linux** — `/memory` command broken until fixed (see above)
2. **MCP unavailable** — nautilus.exe won't run. `get_mcp_servers()` will print a yellow warning and return empty list. Agent degrades gracefully (runs without tools).
3. **Bedrock token may be expired** — the bearer token in the old `.env` has unknown expiry. Don't rely on it; use Ollama as primary.
4. **Two entry points** — `kdev.py` vs `kdev/` package. The monolith (`kdev.py`) is the one with all features. Don't confuse them.
5. **`skills.py` must be co-located** — `kdev.py` does `from skills import ...` — `skills.py` must be in the same directory as `kdev.py`.
6. **pydantic-ai API** — built against a specific version. If you reinstall and get import errors on `ModelRequest`, `TextPart`, etc., pin the version: `pip3 install "pydantic-ai==<version-from-windows>"`.
7. **Python version** — kdev was written on Python 3.14. Some syntax (e.g. `str | None` type unions, `except*`) requires Python 3.11+. Should be fine on Ubuntu 22.04+ (ships 3.10; use deadsnakes PPA for 3.11+ if needed).

---

## First Thing To Do On Linux Boot

```bash
# 1. Navigate to workspace
cd ~/yanflareplayground   # or wherever it landed

# 2. Check Python
python3 --version         # need 3.11+

# 3. Install dependencies
pip3 install "pydantic-ai==1.67.0" "httpx==0.28.1" "rich==14.3.3" \
             "prompt_toolkit==3.0.52" "python-dotenv==1.2.1" "openai==2.26.0"

# 4. Check Ollama
curl http://localhost:11434/api/tags
ollama list               # verify qwen2.5-abliterate:14b-instruct-q4_K_M is present

# 5. Create .env
cp .env.example .env
nano .env
# Set: OLLAMA_BASE_URL=http://localhost:11434
#      OLLAMA_MODEL=qwen2.5-abliterate:14b-instruct-q4_K_M

# 6. Test it
python3 kdev.py "hello, confirm you are running on Linux with Ollama"

# 7. Read MIGRATION_CHECKLIST.md for the full list of things to fix
```

---

## Architecture Quick Reference

```
kdev.py                 ← RUN THIS. Monolith. All features.
skills.py               ← Self-learning. Must be in same dir as kdev.py.
.env                    ← Backend config. RECREATE ON LINUX.
.agent.md               ← Workspace memory. Injected into every session.
kdev/                   ← Modular refactor (secondary, no streaming/skills)
docs/PLAN.md            ← Architecture notes + roadmap
MIGRATION_CHECKLIST.md  ← Detailed file-by-file migration notes
~/.kdev/                ← All runtime data (sessions, skills, history)
```

---

## Key Design Decisions (from Windows session)

- **BedrockBearerModel uses streaming** (`invoke-with-response-stream`) — tokens print live. The `kdev/backends.py` version is non-streaming (uses `/invoke` directly) — this is intentional for the modular package which is simpler.
- **Ollama speaks OpenAI-compatible API** — `pydantic-ai`'s `OpenAIModel` is used with `base_url=f"{OLLAMA_BASE_URL}/v1"` — no special Ollama client needed.
- **Qwen3 is a thinking model** — `kdev.py` detects this via `is_thinking_model()` and switches to `SYSTEM_PROMPT_THINKING` which explicitly instructs the model to confine reasoning to `<think>` tags. The streaming code filters these to `◌ first line…` display.
- **MCP graceful degradation** — if nautilus fails (timeout, not found), the agent falls back through: all servers → nautilus-only → no MCP. Never crashes.
- **`skills.py` is separate from `kdev/`** — by design. The monolith `kdev.py` imports it directly. The modular package doesn't use it yet.

---

*This document was written by the Windows instance of kdev on 2026-03-14, before the Linux PC arrived. If anything in here is wrong or outdated, update it for the next boot.*
---
## Reasoning Protocol (Permanent)
When faced with any non-trivial request, you MUST follow these steps before answering:
1. Restate the problem in your own words in one sentence
2. Identify the problem type (debugging / design / explanation / planning / other)
3. State any assumptions you are making
4. Consider at least 2 approaches before choosing one
5. Then provide your answer
For simple requests, steps 1-2 are sufficient. Never skip this process entirely.
This is a core behavior, not optional.
---
