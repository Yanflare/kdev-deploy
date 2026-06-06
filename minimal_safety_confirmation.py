import pathlib

TARGET = pathlib.Path('/home/yanflare/kdev-deploy/kdev_tools.py')
content = TARGET.read_text(encoding='utf-8')

# Minimal safety check inserted at the start of ShellExec.call
safety_check = '''
        # === MINIMAL SAFETY CONFIRMATION GATE ===
        cmd = args.get("cmd", args_str) if isinstance(args, dict) else args_str
        if any(kw in str(cmd).lower() for kw in ["rm -f", "rm -rf", "rm ", "rmdir", "unlink", " > ", " >> ", "dd ", "mkfs", "shred", "wipe", "chmod ", "chown ", "mv ", "cp -f"]):
            return (
                "⚠️ SAFETY CONFIRMATION REQUIRED\\n\\n"
                f"Command: `{cmd}`\\n\\n"
                "Reply with **YES** to allow once, or **NO** to cancel."
            )
'''

# Insert the check right after the try: json.loads line
insert_point = content.find("try:")
if insert_point != -1:
    insert_point = content.find("args = json.loads", insert_point)
    if insert_point != -1:
        insert_point = content.find("\n", insert_point) + 1
        content = content[:insert_point] + safety_check + content[insert_point:]

TARGET.write_text(content, encoding='utf-8')
print("✅ Minimal safety confirmation inserted into ShellExec")
