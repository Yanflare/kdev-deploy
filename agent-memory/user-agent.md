## About Me
- Running kdev on Linux (migrated from Windows 2026-03-14)
- Primary LLM: Ollama local, model qwen2.5-abliterate:14b-instruct-q4_K_M
- This is a 14b model — not a thinking model, no <think> blocks

## Preferences
- Prefer concise, direct responses — skip preamble
- Always read code before editing — no guessing at structure
- Tasks should be broken down and completed one at a time without chaining multiple actions unprompted
- Avoid complex actions without explicit instructions
- The `/memory` command currently opens files with an editor but does not specify which editor. Users can set their preferred editor via environment variables.

## Known Platform Issues (Linux)
- /memory command: os.startfile() is Windows-only — avoid
- MCP tools (nautilus): Windows binary, unavailable — agent degrades gracefully