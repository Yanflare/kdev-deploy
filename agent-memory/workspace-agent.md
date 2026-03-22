# Workspace Memory

- This is the kdev workspace — the agent's own source code
- **Active entry point**: `kdev.py` (monolith, ~945 lines) — has streaming, skills, thinking model support
- Package entry (secondary): `kdev/main.py` → `run_agent_loop()` in `kdev/agent.py` — no streaming/skills
- Active backend: AWS Bedrock via bearer token (`AWS_BEARER_TOKEN_BEDROCK`) on Windows; Ollama (`huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M`) on Linux
- MCP tools come from nautilus exe at `~/.rovodev/.local/share/acli/1.3.13-stable/...` (Windows only — .exe binary)
- Sessions saved to `~/.kdev/sessions/<uuid>/context.json`
- User-level memory at `~/.kdev/agent.md`; workspace memory here (`.agent.md`)
- Debug mode: set `KDEV_DEBUG=1` in `.env`
- `skills.py` must be co-located with `kdev.py` — imported directly, not part of the `kdev/` package

## Session Note — 2026-03-14 (Pre-migration)

- **Migration imminent**: Linux headless PC arriving soon. Windows → Ubuntu.
- **Key decisions this session**:
  - Confirmed `kdev.py` monolith is the active entry point (not `kdev/` package)
  - Audited all Windows-specific assumptions: hardcoded `C:\Users\Kristian\...` nautilus path, `os.startfile()` calls
  - `kdev/memory.py` and `kdev.py` both have hardcoded Windows nautilus path — will fail gracefully (exe not found → no MCP), but `/memory` command will crash (`os.startfile` is Windows-only)
  - Ollama backend already wired in `build_model()` — just needs `.env` with `OLLAMA_BASE_URL` + `OLLAMA_MODEL=huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M`
  - `huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M` is the sole model — no thinking variant, no `<think>` filtering needed
- **Migration docs created**:
  - `MIGRATION_CHECKLIST.md` — file-by-file changes needed, Linux `.env` template, verification steps
  - `LINUX_BOOT_PROMPT.md` — full briefing for first Linux session (read this first on boot)
- **Deployment package created**: `kdev-deploy/` folder — complete self-contained package for SCP to Linux


## Discussion Mode Rules
If the user uses words like: hypothetically, theoretically, how would you, thought process — switch to DISCUSSION MODE.
In discussion mode: do NOT execute any commands, do NOT look for files, respond only in text.
Stay in discussion mode until the user gives a real task.
