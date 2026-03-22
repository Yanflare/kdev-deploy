# kdev_tools.py — KDEV tool registry
# Session 9 — 2026-03-22
#
# Inspired by Qwen-Agent's BaseTool/register_tool pattern (Apache-2.0)
# Inlined — zero external dependencies beyond stdlib + requests.
# requests is already in the venv (kdev_web.py uses it for SearXNG).
#
# Tools registered: shell_exec, file_read, file_write, skill_save, web_search
#
# Public API:
#   TOOL_REGISTRY              — dict of name -> class
#   build_tools_system_prompt() -> str   (append to SYSTEM_PROMPT)

import json
import subprocess
import requests
from pathlib import Path
from datetime import datetime

# ── Inlined BaseTool + register_tool (qwen-agent pattern, no import needed) ───

TOOL_REGISTRY = {}

def register_tool(name):
    """Class decorator: registers the tool class under `name`."""
    def decorator(cls):
        TOOL_REGISTRY[name] = cls
        cls.tool_name = name
        return cls
    return decorator

class BaseTool:
    description: str = ''
    parameters: list = []

    def call(self, params: str, **kwargs) -> str:
        raise NotImplementedError

# ── 1. shell_exec ─────────────────────────────────────────────────────────────

@register_tool('shell_exec')
class ShellExec(BaseTool):
    description = 'Run a shell command on the Linux host and return stdout/stderr.'
    parameters = [
        {'name': 'cmd', 'type': 'string',
         'description': 'The shell command to execute.', 'required': True}
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            cmd = json.loads(params)['cmd']
        except Exception as e:
            return json.dumps({'returncode': -1, 'output': f'ARGS_PARSE_ERROR: {e}'})
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True,
                                    text=True, timeout=30)
            output = (result.stdout + result.stderr)[:4000]
            return json.dumps({'returncode': result.returncode, 'output': output})
        except subprocess.TimeoutExpired:
            return json.dumps({'returncode': -1, 'output': 'TIMEOUT: command exceeded 30s'})
        except Exception as e:
            return json.dumps({'returncode': -1, 'output': f'EXEC_ERROR: {e}'})


# ── 2. file_read ──────────────────────────────────────────────────────────────

@register_tool('file_read')
class FileRead(BaseTool):
    description = 'Read a file from disk and return its contents (max 8000 chars).'
    parameters = [
        {'name': 'path', 'type': 'string',
         'description': 'Absolute path to the file.', 'required': True}
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            path = json.loads(params)['path']
        except Exception as e:
            return f'ARGS_PARSE_ERROR: {e}'
        try:
            return Path(path).read_text(errors='replace')[:8000]
        except Exception as e:
            return f'FILE_READ_ERROR: {e}'


# ── 3. file_write ─────────────────────────────────────────────────────────────

@register_tool('file_write')
class FileWrite(BaseTool):
    description = 'Write content to a file on disk, creating it if it does not exist.'
    parameters = [
        {'name': 'path', 'type': 'string',
         'description': 'Absolute path to the file.', 'required': True},
        {'name': 'content', 'type': 'string',
         'description': 'Full content to write.', 'required': True}
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            path, content = p['path'], p['content']
        except Exception as e:
            return json.dumps({'ok': False, 'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            return json.dumps({'ok': True, 'path': str(path), 'bytes': len(content)})
        except Exception as e:
            return json.dumps({'ok': False, 'error': f'WRITE_ERROR: {e}'})


# ── 4. skill_save ─────────────────────────────────────────────────────────────

@register_tool('skill_save')
class SkillSave(BaseTool):
    description = (
        'Save a reusable skill to ~/.kdev/skills/ so it is injected in future sessions. '
        'Use when you solve something non-trivial that should be remembered.'
    )
    parameters = [
        {'name': 'name', 'type': 'string',
         'description': 'Short identifier — lowercase, hyphens ok, no spaces.', 'required': True},
        {'name': 'content', 'type': 'string',
         'description': 'Full skill markdown content.', 'required': True}
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            name, content = p['name'], p['content']
        except Exception as e:
            return json.dumps({'ok': False, 'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            skills_dir = Path.home() / '.kdev' / 'skills'
            skills_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime('%Y%m%d-%H%M%S')
            fname = f'{ts}-{name}.md'
            (skills_dir / fname).write_text(content)
            return json.dumps({'ok': True, 'saved': str(skills_dir / fname)})
        except Exception as e:
            return json.dumps({'ok': False, 'error': f'SAVE_ERROR: {e}'})


# ── 5. web_search ─────────────────────────────────────────────────────────────
# SearXNG call inlined — avoids any circular import with kdev_web.py

SEARXNG_URL = 'http://localhost:4000'

@register_tool('web_search')
class WebSearch(BaseTool):
    description = 'Search the web via the local SearXNG instance and return top 5 results.'
    parameters = [
        {'name': 'query', 'type': 'string',
         'description': 'The search query.', 'required': True}
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            query = json.loads(params)['query']
        except Exception as e:
            return f'ARGS_PARSE_ERROR: {e}'
        try:
            resp = requests.get(
                f'{SEARXNG_URL}/search',
                params={'q': query, 'format': 'json', 'categories': 'general'},
                timeout=10
            )
            data = resp.json()
            results = data.get('results', [])[:5]
            if not results:
                return '[WEB SEARCH] No results found.'
            lines = [f'[WEB SEARCH] Results for: {query}\n']
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r.get('title', '')}")
                lines.append(f"   URL: {r.get('url', '')}")
                lines.append(f"   {r.get('content', '')[:200]}")
                lines.append('')
            return '\n'.join(lines)
        except Exception as e:
            return f'[WEB SEARCH ERROR] {e}'


# ── Tools system prompt builder ───────────────────────────────────────────────

KDEV_TOOLS = ['shell_exec', 'file_read', 'file_write', 'skill_save', 'web_search']


def build_tools_system_prompt() -> str:
    """
    Render the Qwen2.5 fncall schema block for all KDEV tools.
    Called once at kdev_web.py module load — appended to SYSTEM_PROMPT.
    """
    lines = ['\n\n# Tools\n',
             'You have access to the following tools:\n']

    for name in KDEV_TOOLS:
        if name not in TOOL_REGISTRY:
            continue
        instance = TOOL_REGISTRY[name]()
        lines.append(f'## {name}')
        lines.append(f'Description: {instance.description}')
        lines.append('Parameters:')
        for p in instance.parameters:
            req = '(required)' if p.get('required') else '(optional)'
            lines.append(f"  - {p['name']} ({p['type']}, {req}): {p.get('description', '')}")
        lines.append('')

    lines += [
        '## How to call a tool',
        'Output EXACTLY this format — no prose before the call, no markdown fences:\n',
        '✿FUNCTION✿: <tool_name>',
        '✿ARGS✿: {"arg_name": "value"}\n',
        'The result will be injected as:',
        '✿RESULT✿: <tool output>\n',
        'Then continue your response naturally.',
        'One tool call per turn. Only call tools that exist in the list above.',
    ]

    return '\n'.join(lines)


# ── Self-test — run directly: python3 kdev_tools.py ──────────────────────────

if __name__ == '__main__':
    print('=== Registered tools ===')
    for name in KDEV_TOOLS:
        status = 'OK' if name in TOOL_REGISTRY else 'MISSING'
        print(f'  [{status}] {name}')

    print('\n=== shell_exec smoke test ===')
    r = TOOL_REGISTRY['shell_exec']().call('{"cmd": "echo kdev_tools OK && whoami"}')
    print(r)

    print('\n=== file_read smoke test ===')
    r = TOOL_REGISTRY['file_read']().call('{"path": "/etc/hostname"}')
    print(r)

    print('\n=== Tools system prompt preview (first 500 chars) ===')
    print(build_tools_system_prompt()[:500])

    print('\n=== All checks done ===')
