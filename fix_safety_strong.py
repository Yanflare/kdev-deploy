import pathlib

TARGET = pathlib.Path('/home/yanflare/build2/orchestrator/kdev_safety_layer.py')
content = TARGET.read_text(encoding='utf-8')

new_safety = '''
def emergency_stop(reason, cmd=''):
    """Ask user for explicit YES/NO confirmation"""
    msg = (
        f"⚠️ <b>SAFETY CONFIRMATION REQUIRED</b>\\n\\n"
        f"Command: <code>{cmd}</code>\\n"
        f"Reason: {reason}\\n\\n"
        f"Reply with <b>YES</b> to allow this once, or <b>NO</b> to cancel."
    )
    print(f"[safety] CONFIRMATION REQUESTED: {reason} | cmd={cmd}")
    log_safety_event("dangerous_action", "confirmation_requested", reason, cmd)
    send_telegram(msg)
    return msg   # let orchestrator show this to the user
'''

# Replace the old emergency_stop function
start = content.find("def emergency_stop")
end = content.find("def ", start + 1)
if start != -1 and end != -1:
    content = content[:start] + new_safety + content[end:]

TARGET.write_text(content, encoding='utf-8')
print("✅ Strong safety confirmation gate applied")
