import pathlib

TARGET = pathlib.Path('/home/yanflare/kdev-deploy/kdev_tools.py')
content = TARGET.read_text(encoding='utf-8')

# Fix: make session_id optional with default (or remove it if not needed)
if 'def call(self, args_str: str, session_id: str = "default"):' not in content:
    # Find the HttpRequest class call method
    old_call = 'def call(self, args_str: str, session_id: str = None):'
    if old_call in content:
        content = content.replace(
            old_call,
            'def call(self, args_str: str, session_id: str = "default"):'
        )
    else:
        # Alternative common signature
        content = content.replace(
            'def call(self, args_str: str):',
            'def call(self, args_str: str, session_id: str = "default"):'
        )

TARGET.write_text(content, encoding='utf-8')
print("✅ http_request tool fixed (session_id now has default)")
