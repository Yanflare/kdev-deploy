import pathlib

TARGET = pathlib.Path('/home/yanflare/kdev-deploy/kdev_web.py')
content = TARGET.read_text(encoding='utf-8')

if "CLEANUP: /chat now forwards to 9B Orchestrator by default" in content:
    print("Cleanup already applied.")
else:
    # Modify the original chat_endpoint to forward to orchestrator by default
    old_endpoint = content.find('@app.post("/chat")')
    if old_endpoint != -1:
        # Find the start of the function body
        func_start = content.find("async def chat_endpoint", old_endpoint)
        insert_point = content.find("    if not check_auth", func_start)
        if insert_point != -1:
            routing_code = '''
    # CLEANUP: /chat now forwards to 9B Orchestrator by default
    if request.query.get("legacy") != "1" and request.headers.get("X-Legacy") != "1":
        data = await request.json() if hasattr(request, "json") else await req.json()
        message = data.get("message", "") if isinstance(data, dict) else req.message
        session_id = data.get("session_id") if isinstance(data, dict) else req.session_id
        result = await proxy_to_orchestrator(message, session_id)
        return web.json_response(result)
    # Legacy mode (old 14b ReAct) - only when ?legacy=1 is used
'''
            content = content[:insert_point] + routing_code + content[insert_point:]

    # Optional: update title again for clarity
    content = content.replace("<title>KDEV", "<title>KDEV — 9B Orchestrator + 14b Worker", 1)

    TARGET.write_text(content, encoding='utf-8')
    print("✅ Cleanup applied!")
    print("   → /chat now automatically uses the 9B Orchestrator (default)")
    print("   → ?legacy=1 still works for old 14b ReAct (debug only)")
