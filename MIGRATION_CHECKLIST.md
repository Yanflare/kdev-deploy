# Migration Checklist — Windows → Linux

Generated: 2026-03-14  
Migration target: Ubuntu Linux (headless), accessed via SSH from Windows laptop.

---

## 1. Files That Need Changes on Linux

### `kdev/memory.py` — CRITICAL
**Problem:** Hardcoded absolute Windows path to `nautilus.exe`.
```python
nautilus_exe = Path(
    r"C:\Users\Kristian\.rovodev\.local\share\acli\1.3.13-stable"
    r"\plugin\rovodev\atlassian_cli_rovodev.exe"
)
```
**Fix needed:**
- `atlassian_cli_rovodev.exe` does not run on Linux (Windows PE binary).
- Replace `get_mcp_server()` with a Linux MCP solution (see §4 below).
- Interim: function already degrades gracefully — if exe not found, returns `None` and prints a warning. No code change needed to *run*, but MCP tools will be unavailable until a Linux MCP is configured.

### `kdev.py` (monolithic copy) — CRITICAL
**Problem:** Same hardcoded nautilus path at line ~542:
```python
nautilus_exe = Path(
    r"C:\Users\Kristian\.rovodev\.local\share\acli\1.3.13-stable"
    r"\plugin\rovodev\atlassian_cli_rovodev.exe"
)
```
Also has `os.startfile()` at line ~635 for `/memory` command.
**Fix needed:**
- Same MCP fix as `kdev/memory.py`.
- Replace `os.startfile(str(MEMORY_FILE))` with:
  ```python
  import subprocess
  editor = os.getenv("EDITOR", "nano")
  subprocess.Popen([editor, str(MEMORY_FILE)])
  ```

### `kdev/commands.py` — IMPORTANT
**Problem:** `os.startfile()` call at line ~95 for `/memory` command:
```python
os.startfile(str(MEMORY_FILE))
```
`os.startfile` is Windows-only. Calling it on Linux raises `AttributeError`.
**Fix needed:**
```python
import subprocess, shutil
editor = os.getenv("EDITOR", "nano")
subprocess.Popen([editor, str(MEMORY_FILE)])
```

### `.env` — MUST RECREATE
Current `.env` has Windows-specific Bedrock credentials that will not be valid on Linux (the bearer token may expire; Bedrock won't be the primary backend anyway).
**Create fresh `.env` on Linux** — see §2 below.

### `.claude/settings.local.json` — IGNORE
Contains Claude Code permissions with Windows paths (`C:\\Users\\Kristian\\...`) and Windows commands (`setx`). This file is irrelevant on Linux (it's for Claude Code, not kdev).

### `README.md`, `docs/PLAN.md` — LOW PRIORITY
No path hardcoding, but references to Windows/PowerShell in usage examples are cosmetic only. No functional impact.

### `fat32_format.py` — WINDOWS ONLY
Uses Windows-specific Win32 API / ctypes calls for FAT32 formatting. This file is a utility script for USB formatting on Windows — it will not work on Linux. Do not run it. Mark as Windows-only utility.

---

## 2. Linux `.env` Contents

Create `~/<workspace>/.env` with this content (fill in actual values):

```env
# ── Local Ollama (primary backend on Linux) ────────────────────────────────
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:27b

# ── AWS Bedrock (keep as fallback if token still valid) ─────────────────────
# AWS_BEARER_TOKEN_BEDROCK=<paste token from Windows .env if still valid>
# AWS_REGION=us-east-1
# ANTHROPIC_DEFAULT_SONNET_MODEL=us.anthropic.claude-sonnet-4-6

# ── Direct Anthropic (optional fallback) ────────────────────────────────────
# ANTHROPIC_API_KEY=sk-ant-...

# ── GitHub MCP (optional — enables repo/PR/issue tools) ─────────────────────
# GITHUB_TOKEN=<your github PAT>

# ── Debug ────────────────────────────────────────────────────────────────────
# KDEV_DEBUG=1
```

**Notes:**
- If Ollama is running locally on the Linux box: `OLLAMA_BASE_URL=http://localhost:11434`
- If Ollama is running on a different machine on LAN: `OLLAMA_BASE_URL=http://<LAN-IP>:11434`
- `qwen3:27b` is a thinking model — kdev.py already has `<think>` block handling for it.

---

## 3. Windows → Linux Command Equivalents

| Windows (what the code does)           | Linux equivalent                             | Status         |
|----------------------------------------|----------------------------------------------|----------------|
| `os.startfile(path)` — open in editor  | `subprocess.Popen([os.getenv("EDITOR","nano"), path])` | Must fix in code |
| `atlassian_cli_rovodev.exe` (MCP)      | Needs Linux MCP binary or alternative        | Blocked — TBD  |
| `powershell` shell in MCP tools list   | `bash` shell                                 | In MCP config  |
| `C:\Users\Kristian\...` paths          | `Path.home() / ...` (already used in config) | ✅ Already OK  |
| `Path.home()` → `C:\Users\Kristian`    | `Path.home()` → `/home/<user>`               | ✅ Already OK  |
| `HISTORY_FILE = ~/.kdev/prompt_history`| Same — pathlib handles it                    | ✅ Already OK  |
| `SESSIONS_DIR = ~/.kdev/sessions/`     | Same — pathlib handles it                    | ✅ Already OK  |
| `python kdev.py`                       | `python3 kdev.py` or `python kdev.py`        | Check shebang  |
| Windows line endings (CRLF)            | Git should handle; run `dos2unix` if issues  | Low risk       |
| `.env` loading via python-dotenv       | Same — works on Linux                        | ✅ Already OK  |

### MCP on Linux — Options (TBD):
1. **Check if rovodev releases a Linux binary** — `~/.rovodev/...` — look for a `.tar.gz` or Linux AppImage.
2. **Use filesystem MCP server** — `@modelcontextprotocol/server-filesystem` via npx (needs Node.js).
3. **Run without MCP** — kdev degrades gracefully; agent loses file/shell tools but core chat works.
4. **Build custom stdio MCP in Python** — implement the file tools as a Python MCP server.

---

## 4. Post-Linux-Boot Verification Steps

Run these in order to confirm kdev is working:

```bash
# 1. Verify Python version
python3 --version          # want 3.11+

# 2. Install dependencies (versions confirmed working on Windows 2026-03-14)
cd ~/yanflareplayground     # (or wherever the workspace landed)
pip3 install \
  "pydantic-ai==1.67.0" \
  "httpx==0.28.1" \
  "rich==14.3.3" \
  "prompt_toolkit==3.0.52" \
  "python-dotenv==1.2.1" \
  "openai==2.26.0"
# Or without version pins (may work with newer versions, may break):
# pip3 install pydantic-ai httpx rich prompt_toolkit python-dotenv openai

# 3. Verify Ollama is running
curl http://localhost:11434/api/tags   # should return JSON list of models

# 4. Verify qwen3:27b is pulled
ollama list                            # should show qwen3:27b

# 5. Create .env (see §2 above)
nano .env

# 6. Test single-shot mode
python3 kdev.py "say hello"

# 7. Test interactive mode
python3 kdev.py

# 8. Verify /backend command works
# Inside REPL: /backend ollama:qwen3:27b

# 9. Check MCP status
# Look for "nautilus exe not found" warning — expected on Linux
# Plan Linux MCP solution (see §3 above)

# 10. Run skills.py sanity check
python3 -c "from skills import list_skills; print(list_skills())"
```

---

## 5. Known Issues / Risks

- **Bedrock bearer token expiry**: The token in `.env` is a base64-encoded string — it may have an expiry. Test it before migration if possible.
- **pydantic-ai version pinning**: `kdev/` package was built against a specific pydantic-ai version. If `pip install pydantic-ai` installs a newer version with breaking changes, `ModelRequest/ModelResponse` imports may fail. Pin: check `pip show pydantic-ai` on Windows first.
- **`struct` import in `kdev.py`**: `import struct` is in `kdev.py` (the monolith) but NOT in `kdev/backends.py`. The modular `kdev/` package does NOT use streaming — only the monolith `kdev.py` does. This is fine.
- **Two entry points exist**: `kdev.py` (monolith, has streaming + skills) and `kdev/` package (modular, no streaming, no skills). The monolith is the active one. Ensure `python3 kdev.py` is used, not `python3 -m kdev`.
- **`skills.py` must be in workspace root**: It's imported by `kdev.py` via `from skills import ...`. It is NOT inside the `kdev/` package. Must be present alongside `kdev.py`.
