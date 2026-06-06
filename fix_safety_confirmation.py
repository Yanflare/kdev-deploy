import pathlib

TARGET = pathlib.Path('/home/yanflare/build2/orchestrator/kdev_safety_layer.py')
content = TARGET.read_text(encoding='utf-8')

# Replace the emergency_stop with a confirmation request
new_safety = '''
def emergency_stop(reason, cmd=''):
    """Instead of hard stop, ask user for explicit confirmation"""
    msg = (
        f"⚠️ SAFETY CHECK — Dangerous action detected\\n"
        f"Command: <code>{cmd}</code>\\n"
        f"Reason: {reason}\\n\\n"
        f"Type **YES** to allow this command once, or **NO** to cancel."
    )
    print(f"[safety] CONFIRMATION REQUIRED: {reason}")
    log_safety_event("dangerous_action", "confirmation_requested", reason, cmd)
    send_telegram(msg)
    # Do NOT stop autopilot automatically — wait for user YES/NO
    return msg  # return the message so orchestrator can show it to user
'''

# Update the dangerous action handler to call confirmation instead of hard stop
content = content.replace(
    'def emergency_stop(reason, cmd=""):',
    new_safety
)

# Also update the call site to return the message instead of stopping
content = content.replace(
    'emergency_stop(f" Dangerous action targeting protected path: {path}", cmd)',
    'emergency_stop(f"Dangerous action targeting protected path: {path}", cmd)'
)

TARGET.write_text(content, encoding='utf-8')
print("✅ Safety Layer updated — now asks for explicit YES/NO confirmation instead of hard block")
