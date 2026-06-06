import pathlib

TARGET = pathlib.Path('/home/yanflare/kdev-deploy/kdev_web.py')
content = TARGET.read_text(encoding='utf-8')

if "MINIMAL PHASE 2D SINGLE-URL" in content:
    print("Patch already applied.")
else:
    # Add clean /orch/chat route
    orch_route = '''
# === MINIMAL PHASE 2D SINGLE-URL - 9B Orchestrator as main frontend ===
@app.post("/orch/chat")
async def orch_chat(req: ChatRequest, kdev_session: str | None = Cookie(default=None)):
    if not check_auth(kdev_session):
        return Response("Unauthorized", status_code=401)
    try:
        payload = json.dumps({"message": req.message, "session_id": req.session_id}).encode()
        orch_req = urllib.request.Request(
            "http://localhost:8081/orch/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(orch_req, timeout=300) as resp:
            return web.json_response(json.loads(resp.read()))
    except Exception as e:
        return web.json_response({"type": "ERROR", "final": f"Proxy error: {str(e)}"})
'''

    # Insert the route just before the original @app.post("/chat")
    insert_pos = content.find('@app.post("/chat")')
    if insert_pos != -1:
        content = content[:insert_pos] + orch_route + content[insert_pos:]

    # Update the frontend JS to call /orch/chat by default
    content = content.replace('url: "/chat",', 'url: "/orch/chat",', 1)

    # Nice title
    content = content.replace("<title>KDEV", "<title>KDEV — 9B Orchestrator + 14b Worker", 1)

    TARGET.write_text(content, encoding='utf-8')
    print("✅ Minimal single-URL patch applied!")
    print("   → Browser now calls /orch/chat (9B Orchestrator)")
    print("   → Old /chat still exists for legacy=1 debugging")
