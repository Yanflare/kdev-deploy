## Current content of agent-memory/user-agent.md:
# User Memory — kdev global context

Injected into every kdev session across all workspaces.

## About Me
- Running kdev on Linux (migrated from Windows 2026-03-14)
- Primary LLM: Ollama local, model qwen2.5-abliterate:14b-instruct-q4_K_M
- This is a 14b model — not a thinking model, no <think> blocks

## Preferences
- Prefer concise, direct responses — skip preamble
- Always read code before editing — no guessing at structure
- One task at a time — do not chain multiple actions unprompted
- Avoid complex actions without explicit instructions

## Known Platform Issues (Linux)
- /memory command: os.startfile() is Windows-only — avoid
- MCP tools (nautilus): Windows binary, unavailable — agent degrades gracefully