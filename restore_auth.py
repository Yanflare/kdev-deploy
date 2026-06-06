import pathlib

TARGET = pathlib.Path('/home/yanflare/kdev-deploy/kdev_web.py')
content = TARGET.read_text(encoding='utf-8')

# Restore the login check in chat_endpoint
if "if not check_auth(kdev_session):" not in content:
    # Find the chat_endpoint and make sure the auth check is present
    chat_start = content.find("async def chat_endpoint")
    if chat_start != -1:
        insert_point = content.find("    global chat_history", chat_start)
        if insert_point != -1:
            auth_code = '''    if not check_auth(kdev_session):
        return Response("Unauthorized", status_code=401)
'''
            content = content[:insert_point] + auth_code + content[insert_point:]

TARGET.write_text(content, encoding='utf-8')
print("✅ Authentication restored (password prompt should return)")
