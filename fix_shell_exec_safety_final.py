import pathlib

TARGET = pathlib.Path('/home/yanflare/kdev-deploy/kdev_tools.py')
content = TARGET.read_text(encoding='utf-8')

# Minimal, robust ShellExec with built-in safety confirmation
new_shell = '''
class ShellExec:
    def call(self, args_str: str, session_id: str = "default"):
        import json, subprocess

        try:
            args = json.loads(args_str)
            cmd = args.get("cmd", args_str)
        except:
            cmd = args_str

        # === SAFETY CONFIRMATION (double-edged sword) ===
        dangerous = any(kw in cmd.lower() for kw in [
            "rm -f", "rm -rf", "rm ", "rmdir", "unlink", " > ", " >> ", 
            "dd ", "mkfs", "shred", "wipe", "chmod ", "chown ", "mv ", "cp -f"
        ])

        if dangerous:
            return (
                "⚠️ SAFETY CONFIRMATION REQUIRED\\n\\n"
                f"Command: `{cmd}`\\n\\n"
                "Type **YES** to allow once, or **NO** to cancel."
            )

        # Normal execution
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            return {"returncode": result.returncode, "output": result.stdout + result.stderr}
        except Exception as e:
            return {"returncode": -1, "output": str(e)}
'''

# Replace the entire ShellExec class
start = content.find("class ShellExec")
if start != -1:
    end = content.find("class ", start + 1)
    if end == -1:
        end = len(content)
    content = content[:start] + new_shell + content[end:]

TARGET.write_text(content, encoding='utf-8')
print("✅ Final safe ShellExec + confirmation gate applied")
