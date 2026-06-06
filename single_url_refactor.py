import pathlib

TARGET = pathlib.Path('/home/yanflare/kdev-deploy/kdev_web.py')
content = TARGET.read_text(encoding='utf-8')

# === PHASE 2D SINGLE-URL REFACTOR — 9B Orchestrator becomes the main entrypoint ===
orchestrator_proxy = '''
# === PHASE 2D SINGLE-URL REFACTOR (9B Orchestrator as default on port 8080) ===
import urllib.request
import json

ORCH_BRIDGE_URL = "http://localhost:8081/orch/chat"

async def proxy_to_orchestrator(message: str, session_id: str = None):
    """Forward request to 9B orchestrator bridge"""
    payload = json.dumps({
        "message": message,
        "session_id": session_id
    }).encode()

    req = urllib.request.Request(
        ORCH_BRIDGE_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())

# In the main chat route (we inject this logic right before the existing chat handler)
'''

# Safe insertion point: after all imports but before the app routes
insert_pos = content.find("app = web.Application()")
if insert_pos == -1:
    insert_pos = content.find("from fastapi import FastAPI") + 100  # fallback

if "PHASE 2D SINGLE-URL REFACTOR" not in content:
    content = content[:insert_pos] + "\n" + orchestrator_proxy + "\n" + content[insert_pos:]

# Update the main chat handler to use orchestrator by default
content = content.replace(
    "async def chat(",
    '''async def chat(
    # DEFAULT PATH: 9B Orchestrator (single URL experience)
    if not request.query.get("legacy") and request.headers.get("X-Legacy") != "1":
        data = await request.json()
        result = await proxy_to_orchestrator(data.get("message", ""), data.get("session_id"))
        return web.json_response(result)
    # Legacy 14b ReAct path (for debugging)
''',
    1
)

# Cosmetic: update page title and header
content = content.replace("<title>KDEV", "<title>KDEV — 9B Orchestrator + 14b Sub-Agent")
content = content.replace("KDEV Web UI", "KDEV — 9B Orchestrator + 14b Sub-Agent")

TARGET.write_text(content, encoding='utf-8')
print("✅ Single-URL refactor applied successfully!")
print("   → http://192.168.0.117:8080 is now the 9B Orchestrator entrypoint")
print("   → Legacy 14b path still available via ?legacy=1")
print("Next step: restart and test")
