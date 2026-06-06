import pathlib

TARGET = pathlib.Path('/home/yanflare/build2/orchestrator/kdev_safety_layer.py')
content = TARGET.read_text(encoding='utf-8')

# Replace hard emergency_stop with user confirmation request
new_safety = '''
def emergency_stop(reason, cmd=''):
    """Ask user for explicit YES/NO confirmation instead of hard stop"""
    msg = (
        f"⚠️ <b>SAFETY CONFIRMATION REQUIRED</b>\\n\\n"
        f"Command: <code>{cmd}</code>\\n"
        f"Reason: {reason}\\n\\n"
        f"Type <b>YES</b> to allow this once, or <b>NO</b> to cancel."
    )
    print(f"[safety] CONFIRMATION REQUESTED: {reason}")
    log_safety_event("dangerous_action", "confirmation_requested", reason, cmd)
    send_telegram(msg)
    return msg  # return message so orchestrator can display it
'''

# Update detect_dangerous_action to be more sensitive
new_detect = '''
def detect_dangerous_action(events):
    for event in events:
        content = json.dumps(event).lower()
        cmd = str(event.get('args', {}).get('cmd', '')).lower()
        dangerous_keywords = ["rm -f", "rm -rf", "rm ", "rmdir", "unlink", " > ", " >> ", "dd ", "mkfs", "shred", "wipe", "chmod ", "chown ", "mv ", "cp -f"]
        for kw in dangerous_keywords:
            if kw in cmd or kw in content:
                path = next((p for p in PROTECTED_PATHS if p.lower() in content), "unknown path")
                return True, path, cmd
    return False, "", ""
'''

# Apply the changes
content = content.replace(
    'def emergency_stop(reason, cmd=""):',
    new_safety
)

content = content.replace(
    'def detect_dangerous_action(events):',
    new_detect
)

TARGET.write_text(content, encoding='utf-8')
print("✅ Safety Layer updated — now asks for explicit YES/NO confirmation")
