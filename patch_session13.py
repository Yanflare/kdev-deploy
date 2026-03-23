"""
Session 13 patch — wire session_id into kdev_web.py
Apply with: python3 patch_session13.py
Run from:   /home/yanflare/kdev-deploy/
"""
from pathlib import Path

TARGET = Path(__file__).parent / "kdev_web.py"
src = TARGET.read_text(encoding="utf-8")

CHANGES = [
    # 1. Add uuid import
    (
        "import hashlib, json, re, subprocess, sys",
        "import hashlib, json, re, subprocess, sys, uuid"
    ),

    # 2. dispatch_fncall signature only — no docstring, no flower brackets
    (
        "def dispatch_fncall(fn_name: str, args_str: str) -> str:",
        "def dispatch_fncall(fn_name: str, args_str: str, session_id: str = 'default') -> str:"
    ),

    # 3. Forward session_id in the actual tool call inside dispatch_fncall
    (
        "        result = KDEV_TOOL_REGISTRY[fn_name]().call(args_str)",
        "        result = KDEV_TOOL_REGISTRY[fn_name]().call(args_str, session_id=session_id)"
    ),

    # 4. Generate session_id once per conversation in chat_endpoint
    (
        "    global chat_history\n    # /map shortcut: build and return repomap directly, skip LLM",
        "    global chat_history\n    session_id = str(uuid.uuid4())  # unique per conversation\n    # /map shortcut: build and return repomap directly, skip LLM"
    ),

    # 5. Pass session_id through at the exec loop call site
    (
        "                exec_result = dispatch_fncall(fn_name, args_str)",
        "                exec_result = dispatch_fncall(fn_name, args_str, session_id=session_id)"
    ),
]

for old, new in CHANGES:
    if old not in src:
        print(f"[FAIL] Could not find target string — patch aborted.\nSnippet: {old[:80]!r}")
        raise SystemExit(1)
    src = src.replace(old, new, 1)
    print(f"[OK] Applied: {old[:60]!r}")

TARGET.write_text(src, encoding="utf-8")
print("\n[DONE] kdev_web.py patched. Now run:")
print("  sudo systemctl restart kdev-web")
print("  sudo systemctl status kdev-web")
