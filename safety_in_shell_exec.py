import pathlib

TARGET = pathlib.Path('/home/yanflare/kdev-deploy/kdev_tools.py')
content = TARGET.read_text(encoding='utf-8')

# Add confirmation logic inside ShellExec.call
new_call = '''
    def call(self, args_str: str, session_id: str = "default"):
        import json, re
        try:
            args = json.loads(args_str)
            cmd = args.get("cmd", "")
        except:
            cmd = args_str

        # Dangerous command detection
        dangerous = any(kw in cmd.lower() for kw in [
            "rm -f", "rm -rf", "rm ", "rmdir", "unlink", " > ", " >> ", "dd ", 
            "mkfs", "shred", "wipe", "chmod ", "chown ", "mv ", "cp -f"
        ])

        if dangerous:
            return f"⚠️ SAFETY CONFIRMATION REQUIRED\\n\\nCommand: {cmd}\\n\\nReply with **YES** to allow once or **NO** to cancel."

        # Normal execution
        import subprocess
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            return {"returncode": result.returncode, "output": result.stdout + result.stderr}
        except Exception as e:
            return {"returncode": -1, "output": str(e)}
'''

# Replace the existing ShellExec.call method
start = content.find("class ShellExec")
if start != -1:
    call_start = content.find("def call(self", start)
    if call_start != -1:
        call_end = content.find("    def ", call_start + 1)
        if call_end == -1:
            call_end = content.find("class ", call_start + 1)
        content = content[:call_start] + new_call + content[call_end:]

TARGET.write_text(content, encoding='utf-8')
print("✅ Safety confirmation now inside ShellExec tool (catches commands from 14b worker)")
