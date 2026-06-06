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
import os
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
        import re as _re
        try:
            _args = json.loads(params)
            # Alias common alternate key names the 9B occasionally sends
            cmd = _args.get('cmd') or _args.get('command') or _args.get('shell') or _args.get('exec')
            if not cmd:
                return json.dumps({'returncode': -1, 'output': f'ARGS_PARSE_ERROR: no cmd/command key found in {list(_args.keys())}'})
        except Exception as e:
            return json.dumps({'returncode': -1, 'output': f'ARGS_PARSE_ERROR: {e}'})
        # T3-I pip call guard — block autonomous pip install/upgrade
        _PIP_GUARD = _re.compile(
            r'(?:^|\s|/)pip3?\s+(?:install|install\s+-[^\s]*|install\s+--upgrade)',
            _re.IGNORECASE
        )
        if _PIP_GUARD.search(cmd):
            return json.dumps({
                'returncode': -1,
                'output': (
                    'BLOCKED: pip install requires human confirmation. '
                    'Tell the user what you want to install and why.'
                )
            })
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
            return Path(os.path.expanduser(path)).read_text(errors='replace')[:8000]
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

# -- Metric store (ported from snoglobe/helios metrics/) --

import sqlite3 as _sqlite3
import math as _math
import re as _re
import time as _mtime

_METRIC_DB_PATH = Path.home() / '.kdev' / 'memory.db'


def _metric_db():
    db = _sqlite3.connect(str(_METRIC_DB_PATH))
    db.row_factory = _sqlite3.Row
    db.executescript(
        'CREATE TABLE IF NOT EXISTS metric_points ('
        '    id          INTEGER PRIMARY KEY AUTOINCREMENT,'
        '    task_id     TEXT    NOT NULL,'
        '    metric_name TEXT    NOT NULL,'
        '    value       REAL    NOT NULL,'
        '    ts          INTEGER NOT NULL'
        ');'
        'CREATE INDEX IF NOT EXISTS idx_metric_task'
        '    ON metric_points (task_id, metric_name, ts);'
    )
    db.commit()
    return db


class MetricStore:
    def add(self, task_id: str, metric_name: str, value: float) -> None:
        now_ms = int(_mtime.time() * 1000)
        window_ms = 30 * 1000
        db = _metric_db()
        dup = db.execute(
            'SELECT 1 FROM metric_points WHERE task_id=? AND metric_name=? AND value=? AND ts >= ? LIMIT 1',
            (task_id, metric_name, value, now_ms - window_ms)
        ).fetchone()
        if dup:
            db.close()
            return
        db.execute(
            'INSERT INTO metric_points (task_id, metric_name, value, ts) VALUES (?,?,?,?)',
            (task_id, metric_name, value, now_ms)
        )
        db.commit()
        db.close()

    def get_points(self, task_id: str, metric_name: str) -> list:
        db = _metric_db()
        rows = db.execute(
            'SELECT value, ts FROM metric_points WHERE task_id=? AND metric_name=? ORDER BY ts',
            (task_id, metric_name)
        ).fetchall()
        db.close()
        return [{'value': r['value'], 'ts': r['ts']} for r in rows]

    def get_task_summary(self, task_id: str) -> dict:
        db = _metric_db()
        rows = db.execute(
            'SELECT metric_name, value FROM metric_points WHERE task_id=? ORDER BY ts',
            (task_id,)
        ).fetchall()
        db.close()
        buckets = {}
        for r in rows:
            name = r['metric_name']
            v = r['value']
            if name not in buckets:
                buckets[name] = {'values': [], 'min': v, 'max': v}
            buckets[name]['values'].append(v)
            if v < buckets[name]['min']:
                buckets[name]['min'] = v
            if v > buckets[name]['max']:
                buckets[name]['max'] = v
        summary = {}
        for name, b in buckets.items():
            summary[name] = {
                'latest': b['values'][-1],
                'min':    b['min'],
                'max':    b['max'],
                'count':  len(b['values']),
            }
        return summary

    def list_tasks(self) -> list:
        db = _metric_db()
        rows = db.execute(
            'SELECT DISTINCT task_id FROM metric_points ORDER BY task_id'
        ).fetchall()
        db.close()
        return [r['task_id'] for r in rows]


METRIC_STORE = MetricStore()


def parse_metrics(output: str, metric_names: list) -> list:
    patterns = {}
    for name in metric_names:
        escaped = _re.escape(name)
        patterns[name] = _re.compile(
            r'(?:^|\s|,)' + escaped + r'\s*[=:]\s*([+-]?\d+\.?\d*(?:e[+-]?\d+)?)',
            _re.IGNORECASE
        )
    points = []
    now = int(_mtime.time() * 1000)
    for line in output.split('\n'):
        for name, pat in patterns.items():
            m = pat.search(line)
            if m:
                try:
                    v = float(m.group(1))
                    if _math.isfinite(v):
                        points.append({'metric_name': name, 'value': v, 'ts': now})
                except ValueError:
                    pass
    return points


def analyze_metric(points: list, window: int = 20) -> dict:
    if len(points) < 3:
        cur = points[-1]['value'] if points else 0
        return {'trend': 'insufficient_data', 'slope': 0, 'current': cur, 'mean': 0, 'std': 0}
    values = [p['value'] for p in points[-window:]]
    valid  = [v for v in values if _math.isfinite(v)]
    if len(valid) < 3:
        return {'trend': 'unstable', 'slope': 0, 'current': values[-1], 'mean': 0, 'std': 0}
    n    = len(valid)
    mean = sum(valid) / n
    std  = _math.sqrt(sum((v - mean) ** 2 for v in valid) / n)
    xm   = (n - 1) / 2
    num  = sum((i - xm) * (valid[i] - mean) for i in range(n))
    den  = sum((i - xm) ** 2 for i in range(n))
    slope = num / den if den else 0
    thresh = std * 0.1 or 1e-6
    if abs(slope) < thresh:
        trend = 'plateau'
    elif slope < 0:
        trend = 'decreasing'
    else:
        trend = 'increasing'
    return {'trend': trend, 'slope': round(slope, 6), 'current': valid[-1],
            'mean': round(mean, 6), 'std': round(std, 6)}


# -- 6. show_metrics --

@register_tool('show_metrics')
class ShowMetrics(BaseTool):
    description = (
        'Show stored metric values for a running or finished task. '
        'Returns latest/min/max/count and trend (decreasing/plateau/increasing/unstable) '
        'for each metric. task_id format: "machine_id:pid" or any label you used.'
    )
    parameters = [
        {'name': 'task_id', 'type': 'string',
         'description': 'Task identifier (e.g. "local:12345" or "kiki:12345").', 'required': True},
        {'name': 'metric_names', 'type': 'string',
         'description': 'Comma-separated metric names to filter. Omit to show all.', 'required': False},
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            task_id = p['task_id']
            filter_names = [n.strip() for n in p['metric_names'].split(',')] if p.get('metric_names') else None
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})
        summary = METRIC_STORE.get_task_summary(task_id)
        if not summary:
            tasks = METRIC_STORE.list_tasks()
            return json.dumps({'error': f'No metrics for {task_id}', 'available_tasks': tasks})
        if filter_names:
            summary = {k: v for k, v in summary.items() if k in filter_names}
        result = {}
        for name, s in summary.items():
            points = METRIC_STORE.get_points(task_id, name)
            analysis = analyze_metric(points)
            result[name] = {**s, 'trend': analysis['trend'], 'slope': analysis['slope']}
        return json.dumps({'task_id': task_id, 'metrics': result})


# -- 7. compare_runs --

@register_tool('compare_runs')
class CompareRuns(BaseTool):
    description = (
        'Compare metrics between two experiment runs side-by-side. '
        'Shows latest/min/max and delta for each metric. '
        'Use this to decide whether to keep or discard an experiment.'
    )
    parameters = [
        {'name': 'task_a', 'type': 'string',
         'description': 'Baseline task ID.', 'required': True},
        {'name': 'task_b', 'type': 'string',
         'description': 'New task ID to compare against baseline.', 'required': True},
        {'name': 'metric_names', 'type': 'string',
         'description': 'Comma-separated metric names to compare. Omit for all shared metrics.', 'required': False},
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            task_a = p['task_a']
            task_b = p['task_b']
            filter_names = [n.strip() for n in p['metric_names'].split(',')] if p.get('metric_names') else None
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})
        sa = METRIC_STORE.get_task_summary(task_a)
        sb = METRIC_STORE.get_task_summary(task_b)
        if not sa:
            return json.dumps({'error': f'No metrics for {task_a}'})
        if not sb:
            return json.dumps({'error': f'No metrics for {task_b}'})
        all_names = set(list(sa.keys()) + list(sb.keys()))
        names = [n for n in filter_names if n in all_names] if filter_names else sorted(all_names)
        comparisons = []
        for name in names:
            a = sa.get(name)
            b = sb.get(name)
            delta = round(b['latest'] - a['latest'], 6) if a and b else None
            if delta is None:
                direction = 'n/a'
            elif delta < -0.0001:
                direction = 'decreased'
            elif delta > 0.0001:
                direction = 'increased'
            else:
                direction = 'unchanged'
            comparisons.append({
                'metric':     name,
                'baseline':   a,
                'experiment': b,
                'delta':      delta,
                'direction':  direction,
            })
        return json.dumps({'task_a': task_a, 'task_b': task_b, 'comparisons': comparisons})


# -- 8. memory_ls --

@register_tool('memory_ls')
class MemoryLs(BaseTool):
    description = (
        'List the VFS memory tree. Shows paths and one-line gists. '
        'Use path="/" for the full tree, or a subpath like "/experiments/".'
    )
    parameters = [
        {'name': 'path', 'type': 'string',
         'description': 'Directory path to list. Default: "/".', 'required': False},
        {'name': 'session_id', 'type': 'string',
         'description': 'Session ID to query. Omit to use current session.', 'required': False},
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            path       = p.get('path', '/')
            session_id = p.get('session_id') or kwargs.get('session_id', 'default')
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            from kdev_memory import vfs_get
            vfs = vfs_get(session_id)
            return vfs.format_tree(path)
        except Exception as e:
            return json.dumps({'error': str(e)})


# -- 9. memory_read --

@register_tool('memory_read')
class MemoryRead(BaseTool):
    description = 'Read the full content of a VFS memory node by path.'
    parameters = [
        {'name': 'path', 'type': 'string',
         'description': 'Absolute VFS path, e.g. "/goal" or "/experiments/01-baseline".', 'required': True},
        {'name': 'session_id', 'type': 'string',
         'description': 'Session ID. Omit to use current session.', 'required': False},
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            path       = p['path']
            session_id = p.get('session_id') or kwargs.get('session_id', 'default')
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            from kdev_memory import vfs_get
            node = vfs_get(session_id).read(path)
            if node is None:
                return json.dumps({'error': f'Path not found: {path}'})
            return json.dumps({'path': node['path'], 'gist': node['gist'],
                               'content': node['content'], 'is_dir': bool(node['is_dir'])})
        except Exception as e:
            return json.dumps({'error': str(e)})


# -- 10. memory_write --

@register_tool('memory_write')
class MemoryWrite(BaseTool):
    description = (
        'Write a node to VFS memory. Use this to persist goals, observations, '
        'experiment results, or any structured notes across the session. '
        'Prefix path with /global/ to persist across sessions.'
    )
    parameters = [
        {'name': 'path', 'type': 'string',
         'description': 'VFS path, e.g. "/goal" or "/global/hardware".', 'required': True},
        {'name': 'gist', 'type': 'string',
         'description': 'One-line summary shown in tree view.', 'required': True},
        {'name': 'content', 'type': 'string',
         'description': 'Full content of the node. Omit to create a directory node.', 'required': False},
        {'name': 'session_id', 'type': 'string',
         'description': 'Session ID. Omit to use current session.', 'required': False},
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            path       = p['path']
            gist       = p['gist']
            content    = p.get('content', None)
            session_id = p.get('session_id') or kwargs.get('session_id', 'default')
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            from kdev_memory import vfs_get
            vfs_get(session_id).write(path, gist, content)
            return json.dumps({'ok': True, 'path': path})
        except Exception as e:
            return json.dumps({'error': str(e)})



import re as re  # Session 14
# -- ExperimentTracker (Session 14) --
# Writes experiment metadata to /global/experiments/<task_id> in VFS.
# Uses __global__ session so nodes persist across all future sessions.

_GLOBAL_SESSION = "__global__"

def on_experiment_launch(
    task_id: str,
    machine_id: str,
    pid: int,
    command: str,
    log_path: str,
    metric_names: list = None,
) -> None:
    """Write a /global/experiments/<task_id> VFS node on background launch."""
    try:
        import time as _t
        from kdev_memory import vfs_get
        vfs = vfs_get(_GLOBAL_SESSION)
        # Ensure parent directory node exists
        vfs.write(
            "/global/experiments",
            "experiment runs",
            None,
        )
        content_lines = [
            f"task_id:     {task_id}",
            f"machine_id:  {machine_id}",
            f"pid:         {pid}",
            f"command:     {command}",
            f"log_path:    {log_path}",
            f"launched_at: {_t.strftime('%Y-%m-%d %H:%M:%S', _t.localtime())}",
            f"status:      running",
            f"metrics:     {','.join(metric_names) if metric_names else 'none'}",
        ]
        vfs.write(
            f"/global/experiments/{task_id}",
            f"[running] {command[:60]}",
            "\n".join(content_lines),
        )
    except Exception as _e:
        import sys
        print(f"[ExperimentTracker] launch write failed: {_e}", file=sys.stderr)


def on_experiment_complete(
    task_id: str,
    exit_code: int,
    final_metrics: dict = None,
) -> None:
    """Update the VFS node when the experiment finishes (called by metric loop)."""
    try:
        import time as _t
        from kdev_memory import vfs_get
        vfs = vfs_get(_GLOBAL_SESSION)
        node = vfs.read(f"/global/experiments/{task_id}")
        if node is None:
            return
        existing = node["content"] or ""
        # Replace status line
        status = "done" if exit_code == 0 else f"failed (exit {exit_code})"
        updated = re.sub(r"status:\s+running", f"status:      {status}", existing)
        # Append completion timestamp
        updated += f"\nfinished_at: {_t.strftime('%Y-%m-%d %H:%M:%S', _t.localtime())}"
        # Append final metrics if provided
        if final_metrics:
            for k, v in final_metrics.items():
                updated += f"\nfinal_{k}: {v}"
        status_label = "done" if exit_code == 0 else "failed"
        # Re-read command from existing content for gist
        cmd_match = re.search(r"command:\s+(.+)", existing)
        cmd_snippet = cmd_match.group(1)[:60] if cmd_match else task_id
        vfs.write(
            f"/global/experiments/{task_id}",
            f"[{status_label}] {cmd_snippet}",
            updated,
        )
    except Exception as _e:
        import sys
        print(f"[ExperimentTracker] complete write failed: {_e}", file=sys.stderr)

# -- Background metric poller (Session 15) --
# Spawned by ssh_exec_background when metric_names are provided.
# Polls the log every 10 seconds, stores metric points, detects completion.

import asyncio as _asyncio

async def _poll_metrics(task_id, machine_id, log_path, metric_names, interval=10):
    """Poll log file every `interval` seconds, parse metrics, detect completion."""
    import shlex as _sl
    exit_file = log_path + '.exit'
    seen_count = 0
    while True:
        await _asyncio.sleep(interval)
        try:
            result = _run_remote(machine_id, 'tail -n 50 ' + _sl.quote(log_path), timeout=15)
            output = result.get('stdout', '')
            if output:
                points = parse_metrics(output, metric_names)
                new_points = points[seen_count:]
                for pt in new_points:
                    METRIC_STORE.add(task_id, pt['metric_name'], pt['value'])
                seen_count = len(points)
        except Exception as _pe:
            import sys
            print('[_poll_metrics] tail error: ' + str(_pe), file=sys.stderr)
        try:
            exit_result = _run_remote(
                machine_id,
                'cat ' + _sl.quote(exit_file) + ' 2>/dev/null',
                timeout=5,
            )
            exit_str = exit_result.get('stdout', '').strip()
            if exit_str.lstrip('-').isdigit():
                exit_code = int(exit_str)
                summary = METRIC_STORE.get_task_summary(task_id)
                final = {k: v['latest'] for k, v in summary.items()} if summary else None
                on_experiment_complete(task_id, exit_code, final)
                break
        except Exception:
            pass


# -- SSH tools (multi-machine extension, Helios remote pattern) --

import subprocess as _sp
import shlex as _shlex

_MACHINES_PATH = Path.home() / '.kdev' / 'machines.json'


def _load_machines() -> dict:
    if not _MACHINES_PATH.exists():
        return {'local': {'host': 'localhost', 'user': 'local', 'port': 22, 'key_path': None}}
    try:
        return json.loads(_MACHINES_PATH.read_text())
    except Exception:
        return {'local': {'host': 'localhost', 'user': 'local', 'port': 22, 'key_path': None}}


def _ssh_cmd_prefix(machine_id: str) -> list:
    if machine_id == 'local':
        return []
    machines = _load_machines()
    if machine_id not in machines:
        raise ValueError(f'Unknown machine: {machine_id}. Add it to ~/.kdev/machines.json')
    m = machines[machine_id]
    cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes']
    if m.get('port') and m['port'] != 22:
        cmd += ['-p', str(m['port'])]
    if m.get('key_path'):
        cmd += ['-i', m['key_path']]
    cmd.append(f"{m['user']}@{m['host']}")
    return cmd


def _run_remote(machine_id: str, command: str, timeout: int = 30) -> dict:
    prefix = _ssh_cmd_prefix(machine_id)
    if prefix:
        full_cmd = prefix + [command]
        result = _sp.run(full_cmd, capture_output=True, text=True, timeout=timeout)
    else:
        result = _sp.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
    return {
        'stdout':    result.stdout[:4000],
        'stderr':    result.stderr[:2000],
        'exit_code': result.returncode,
    }


# -- 11. ssh_exec --

@register_tool('ssh_exec')
class SshExec(BaseTool):
    description = (
        'Run a short shell command on a named machine (local or remote via SSH). '
        'Returns stdout, stderr, exit_code. For commands that take more than ~30s '
        'use ssh_exec_background instead. '
        'machine_id "local" runs on this machine directly. '
        'Other machine IDs must be configured in ~/.kdev/machines.json.'
    )
    parameters = [
        {'name': 'machine_id', 'type': 'string',
         'description': 'Machine to run on. Use "local" for this machine.', 'required': True},
        {'name': 'command', 'type': 'string',
         'description': 'Shell command to execute.', 'required': True},
        {'name': 'timeout', 'type': 'string',
         'description': 'Timeout in seconds (default 30).', 'required': False},
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            machine_id = p['machine_id']
            command    = p['command']
            timeout    = int(p.get('timeout', 30))
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            return json.dumps(_run_remote(machine_id, command, timeout))
        except Exception as e:
            return json.dumps({'error': str(e)})


# -- 12. ssh_exec_background --

@register_tool('ssh_exec_background')
class SshExecBackground(BaseTool):
    description = (
        'Launch a long-running command in the background on a named machine. '
        'Uses nohup so the process survives SSH disconnection. '
        'Returns pid and log_path. Stdout/stderr go to log_path. '
        'Use ssh_tail to watch the log. Use ssh_exec with "kill -0 <pid>" to check liveness. '
        'Exit code is written to log_path.exit when the process finishes.'
    )
    parameters = [
        {'name': 'machine_id', 'type': 'string',
         'description': 'Machine to run on. Use "local" for this machine.', 'required': True},
        {'name': 'command', 'type': 'string',
         'description': 'Command to run in the background.', 'required': True},
        {'name': 'log_path', 'type': 'string',
         'description': 'Path for stdout/stderr log. Auto-generated if omitted.', 'required': False},
        {'name': 'metric_names', 'type': 'string',
         'description': 'Comma-separated metric names to parse from stdout (key=value format).', 'required': False},
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            machine_id   = p['machine_id']
            command      = p['command']
            log_path     = p.get('log_path') or f'/tmp/kdev-{int(__import__("time").time())}.log'
            metric_names = [n.strip() for n in p['metric_names'].split(',')] if p.get('metric_names') else []
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            # Escape for sh -c wrapper: single-quote the command
            esc_cmd = command.replace("'", "'\\''")
            esc_log = log_path.replace("'", "'\\''")
            wrapped = (
                f"PYTHONUNBUFFERED=1 nohup sh -c '"
                f"{esc_cmd}; echo $? > {esc_log}.exit' "
                f"> {log_path} 2>&1 & echo $!"
            )
            result = _run_remote(machine_id, wrapped, timeout=15)
            if result['exit_code'] != 0:
                return json.dumps({'error': f'launch failed: {result["stderr"]}'})
            pid_str = result['stdout'].strip().split('\n')[-1].strip()
            pid = int(pid_str)
            if pid <= 0:
                raise ValueError(f'invalid PID: {pid_str}')
            task_id = f'{machine_id}:{pid}'
            out = {'pid': pid, 'log_path': log_path, 'machine_id': machine_id, 'task_id': task_id}
            # Register metric collection if requested
            if metric_names:
                out['tracking_metrics'] = metric_names
                out['note'] = 'Use ssh_tail to watch log, then show_metrics to query parsed values'
            # Session 14 — write experiment node to global VFS
            on_experiment_launch(
                task_id=task_id,
                machine_id=machine_id,
                pid=pid,
                command=command,
                log_path=log_path,
                metric_names=metric_names if metric_names else [],
            )
            if metric_names:
                try:
                    loop = _asyncio.get_event_loop()
                    loop.create_task(
                        _poll_metrics(task_id, machine_id, log_path, metric_names, interval=10)
                    )
                    out['poller'] = 'started (10s interval)'
                except Exception as _le:
                    out['poller'] = 'skipped: ' + str(_le)
            return json.dumps(out)
        except Exception as e:
            return json.dumps({'error': str(e)})


# -- 13. ssh_tail --

@register_tool('ssh_tail')
class SshTail(BaseTool):
    description = (
        'Tail the last N lines of a log file on a named machine. '
        'Use this to watch training output from ssh_exec_background jobs.'
    )
    parameters = [
        {'name': 'machine_id', 'type': 'string',
         'description': 'Machine where the log lives.', 'required': True},
        {'name': 'log_path', 'type': 'string',
         'description': 'Absolute path to the log file.', 'required': True},
        {'name': 'lines', 'type': 'string',
         'description': 'Number of lines to return (default 50).', 'required': False},
        {'name': 'task_id', 'type': 'string',
         'description': 'Task ID from ssh_exec_background. Enables metric parsing and completion detection.', 'required': False},
        {'name': 'metric_names', 'type': 'string',
         'description': 'Comma-separated metric names to parse from log output (e.g. "loss,accuracy").', 'required': False},
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            machine_id   = p['machine_id']
            log_path     = p['log_path']
            lines        = int(p.get('lines', 50))
            metric_names = [n.strip() for n in p['metric_names'].split(',')]  \
                           if p.get('metric_names') else []
            task_id      = p.get('task_id')
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            result = _run_remote(machine_id, f'tail -n {lines} {_shlex.quote(log_path)}', timeout=10)
            output = result['stdout'] or ''
            # Session 14 — on-demand metric parsing
            if metric_names and task_id and output:
                points = parse_metrics(output, metric_names)
                for pt in points:
                    METRIC_STORE.add(task_id, pt['metric_name'], pt['value'])
            # Session 14 — check for process completion
            if task_id:
                exit_file = log_path + '.exit'
                try:
                    exit_result = _run_remote(
                        machine_id,
                        f'cat {_shlex.quote(exit_file)} 2>/dev/null',
                        timeout=5,
                    )
                    exit_str = exit_result['stdout'].strip()
                    if exit_str.lstrip('-').isdigit():
                        exit_code = int(exit_str)
                        summary = METRIC_STORE.get_task_summary(task_id)
                        final = {k: v['latest'] for k, v in summary.items()} if summary else None
                        on_experiment_complete(task_id, exit_code, final)
                except Exception:
                    pass  # .exit not found yet — process still running
            return output or f'(log empty or not found: {log_path})'
        except Exception as e:
            return json.dumps({'error': str(e)})



# -- 14. experiment_status --

@register_tool('experiment_status')
class ExperimentStatus(BaseTool):
    description = (
        'List all tracked experiments or read a specific one. '
        'Shows status (running/done/failed), command, log_path, and final metrics. '
        'Omit task_id to list all experiments. '
        'Pair with ssh_tail to get live log output for a running experiment.'
    )
    parameters = [
        {'name': 'task_id', 'type': 'string',
         'description': 'Specific task ID to read. Omit to list all.', 'required': False},
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            task_id = p.get('task_id')
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            from kdev_memory import vfs_get
            vfs = vfs_get(_GLOBAL_SESSION)
            if task_id:
                node = vfs.read(f"/global/experiments/{task_id}")
                if node is None:
                    return json.dumps({'error': f'No experiment found: {task_id}'})
                return json.dumps({'task_id': task_id, 'content': node['content'],
                                   'gist': node['gist']})
            else:
                tree = vfs.format_tree("/global/experiments")
                return tree or 'No experiments tracked yet.'
        except Exception as e:
            return json.dumps({'error': str(e)})




# -- 16. browser_nav ---------------------------------------------------------

PINCHTAB_URL = 'http://localhost:9867'
_pinchtab_headers = {
    'Authorization': 'Bearer kdev-browser',
    'Content-Type': 'application/json',
}


def _pinchtab_default_instance():
    """Return the first running PinchTab instance id, or raise."""
    r = requests.get(
        f'{PINCHTAB_URL}/instances',
        headers=_pinchtab_headers,
        timeout=10,
    )
    r.raise_for_status()
    instances = r.json()
    if isinstance(instances, list):
        for inst in instances:
            if inst.get('status') == 'running':
                return inst['id']
    raise RuntimeError('No running PinchTab instance found')


@register_tool('browser_nav')
class BrowserNav(BaseTool):
    description = (
        'Open a new browser tab and navigate it to a URL using PinchTab headless Chrome. '
        'Returns instance_id and tab_id needed for browser_snap. '
        'Use for web research, reading live pages, and browser automation.'
    )
    parameters = [
        {'name': 'url', 'type': 'string',
         'description': 'Full URL to navigate to (must include https://).', 'required': True},
        {'name': 'instance_id', 'type': 'string',
         'description': 'PinchTab instance ID. Omit to use the default running instance.', 'required': False},
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            url = p['url']
            instance_id = p.get('instance_id') or None
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            if not instance_id:
                instance_id = _pinchtab_default_instance()
            # Step 1: open a new tab
            r1 = requests.post(
                f'{PINCHTAB_URL}/instances/{instance_id}/tabs/open',
                headers=_pinchtab_headers,
                json={},
                timeout=15,
            )
            r1.raise_for_status()
            tab_data = r1.json()
            tab_id = tab_data.get('id') or tab_data.get('tabId') or tab_data.get('tab_id', '')
            if not tab_id:
                return json.dumps({'error': 'tab open returned no tab id', 'raw': tab_data})
            # Step 2: navigate the tab
            r2 = requests.post(
                f'{PINCHTAB_URL}/tabs/{tab_id}/navigate',
                headers=_pinchtab_headers,
                json={'url': url},
                timeout=30,
            )
            r2.raise_for_status()
            return json.dumps({'ok': True, 'instance_id': instance_id, 'tab_id': tab_id, 'url': url})
        except Exception as e:
            return json.dumps({'ok': False, 'error': str(e)})


# -- 17. browser_snap ---------------------------------------------------------

@register_tool('browser_snap')
class BrowserSnap(BaseTool):
    description = (
        'Take a text snapshot of a browser tab using PinchTab. '
        'Returns page structure and interactive elements (~800 tokens, very efficient). '
        'Always call browser_nav first to get instance_id and tab_id.'
    )
    parameters = [
        {'name': 'tab_id', 'type': 'string',
         'description': 'Tab ID returned by browser_nav.', 'required': True},
        {'name': 'filter', 'type': 'string',
         'description': 'Snapshot filter: "interactive" for clickable elements only. Omit for full page.', 'required': False},
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            tab_id = p['tab_id']
            snap_filter = p.get('filter', '')
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            qparams = {}
            if snap_filter:
                qparams['filter'] = snap_filter
            r = requests.get(
                f'{PINCHTAB_URL}/tabs/{tab_id}/snapshot',
                headers=_pinchtab_headers,
                params=qparams,
                timeout=30,
            )
            r.raise_for_status()
            content = r.text
            if len(content) > 6000:
                content = content[:6000] + '...[truncated]'
            return content
        except Exception as e:
            return json.dumps({'error': str(e)})


# -- 18. browser_action -------------------------------------------------------

@register_tool('browser_action')
class BrowserAction(BaseTool):
    description = (
        'Interact with a browser tab using PinchTab: click an element, fill an input, '
        'or press a key. Use element refs (e.g. "e5") from browser_snap output. '
        'Requires tab_id from browser_nav. '
        'Supported kinds: "click" (ref required), "fill" (ref + text required), "press" (key required).'
    )
    parameters = [
        {'name': 'tab_id', 'type': 'string',
         'description': 'Tab ID returned by browser_nav.', 'required': True},
        {'name': 'kind', 'type': 'string',
         'description': 'Action kind: "click", "fill", or "press".', 'required': True},
        {'name': 'ref', 'type': 'string',
         'description': 'Element ref from browser_snap (e.g. "e5"). Required for click and fill.', 'required': False},
        {'name': 'text', 'type': 'string',
         'description': 'Text to fill into an input element. Required for fill.', 'required': False},
        {'name': 'key', 'type': 'string',
         'description': 'Key to press (e.g. "Enter", "Tab"). Required for press.', 'required': False},
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            tab_id = p['tab_id']
            kind   = p['kind']
            ref    = p.get('ref', '')
            text   = p.get('text', '')
            key    = p.get('key', '')
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            if kind == 'click':
                if not ref:
                    return json.dumps({'error': 'click requires ref'})
                body = {'kind': 'click', 'ref': ref}
            elif kind == 'fill':
                if not ref:
                    return json.dumps({'error': 'fill requires ref'})
                body = {'kind': 'fill', 'ref': ref, 'text': text}
            elif kind == 'press':
                if not key:
                    return json.dumps({'error': 'press requires key'})
                body = {'kind': 'press', 'key': key}
            else:
                return json.dumps({'error': f'Unknown action kind: {kind}. Use click, fill, or press.'})
            r = requests.post(
                f'{PINCHTAB_URL}/tabs/{tab_id}/action',
                headers=_pinchtab_headers,
                json=body,
                timeout=30,
            )
            r.raise_for_status()
            try:
                result = r.json()
            except Exception:
                result = {'raw': r.text[:500]}
            return json.dumps({'ok': True, 'kind': kind, 'result': result})
        except Exception as e:
            return json.dumps({'ok': False, 'error': str(e)})


# -- 15. grep_files ------------------------------------------------------------
@register_tool('grep_files')
class GrepFiles(BaseTool):
    description = (
        'Search for a regex pattern across files in a directory. '
        'Uses ripgrep (rg) if available, falls back to pure Python. '
        'Returns matched file paths, line numbers, and line content.'
    )
    parameters = [
        {'name': 'pattern', 'type': 'string',
         'description': 'Regex pattern to search for.', 'required': True},
        {'name': 'path', 'type': 'string',
         'description': 'Directory or file path to search in.', 'required': True},
        {'name': 'file_glob', 'type': 'string',
         'description': 'File glob filter e.g. "*.py" (optional, rg only).', 'required': False},
        {'name': 'max_results', 'type': 'integer',
         'description': 'Maximum number of matches to return (default 50).', 'required': False},
    ]

    def call(self, params: str, **kwargs) -> str:
        import shutil
        import re as _re
        try:
            args = json.loads(params)
            pattern = args['pattern']
            path = args['path']
            file_glob = args.get('file_glob', '')
            max_results = int(args.get('max_results', 50))
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})

        if shutil.which('rg'):
            return self._rg(pattern, path, file_glob, max_results)
        else:
            return self._python_fallback(pattern, path, max_results)

    def _rg(self, pattern, path, file_glob, max_results):
        cmd = ['rg', '--json', '--max-count', '1', pattern, path]
        if file_glob:
            cmd += ['--glob', file_glob]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return json.dumps({'error': 'TIMEOUT: rg exceeded 30s'})
        except Exception as e:
            return json.dumps({'error': f'EXEC_ERROR: {e}'})

        matches = []
        for line in result.stdout.splitlines():
            if len(matches) >= max_results:
                break
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get('type') != 'match':
                continue
            data = obj.get('data', {})
            fpath = data.get('path', {}).get('text', '')
            lineno = data.get('line_number', 0)
            text = data.get('lines', {}).get('text', '').rstrip(chr(10))
            matches.append({'file': fpath, 'line': lineno, 'text': text})

        return json.dumps({
            'engine': 'ripgrep',
            'pattern': pattern,
            'path': path,
            'match_count': len(matches),
            'matches': matches
        })

    def _python_fallback(self, pattern, path, max_results):
        import os
        import re as _re
        matches = []
        try:
            compiled = _re.compile(pattern)
        except Exception as e:
            return json.dumps({'error': f'REGEX_ERROR: {e}'})

        if os.path.isfile(path):
            walk_targets = [(os.path.dirname(path), [], [os.path.basename(path)])]
        else:
            walk_targets = os.walk(path)

        for dirpath, dirnames, filenames in walk_targets:
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and d != '__pycache__']
            for fname in filenames:
                if len(matches) >= max_results:
                    break
                fpath = os.path.join(dirpath, fname)
                try:
                    with open(fpath, 'r', errors='replace') as f:
                        for lineno, text in enumerate(f, 1):
                            if compiled.search(text):
                                matches.append({
                                    'file': fpath,
                                    'line': lineno,
                                    'text': text.rstrip(chr(10))
                                })
                                if len(matches) >= max_results:
                                    break
                except Exception:
                    continue

        return json.dumps({
            'engine': 'python_fallback',
            'pattern': pattern,
            'path': path,
            'match_count': len(matches),
            'matches': matches
        })

@register_tool('http_request')
class HttpRequest(BaseTool):
    name = 'http_request'
    description = (
        'Make a raw HTTP request to a local URL. '
        'Supports GET, POST, PUT, DELETE. '
        'Returns status code, body (capped 4000 chars), and content-type header.'
    )
    parameters = [
        {'name': 'method',  'type': 'string',  'required': True,  'description': 'HTTP verb: GET POST PUT DELETE'},
        {'name': 'url',     'type': 'string',  'required': True,  'description': 'Full URL e.g. http://localhost:11434/api/tags'},
        {'name': 'headers', 'type': 'object',  'required': False, 'description': 'Optional dict of extra request headers'},
        {'name': 'body',    'type': 'object',  'required': False, 'description': 'Optional JSON-serialisable body for POST/PUT'},
        {'name': 'timeout', 'type': 'integer', 'required': False, 'description': 'Request timeout in seconds (default 10)'},
    ]

    def call(self, method='GET', url='', headers=None, body=None, timeout=10):
        import requests as _req
        method = str(method).upper()
        headers = headers or {}
        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            timeout = 10
        if not url:
            return {'error': 'url is required'}
        try:
            resp = _req.request(
                method,
                url,
                headers=headers,
                json=body if body else None,
                timeout=timeout,
            )
            raw = resp.text
            if len(raw) > 4000:
                raw = raw[:4000] + ' ... [truncated]'
            return {
                'status': resp.status_code,
                'body': raw,
                'content_type': resp.headers.get('Content-Type', ''),
            }
        except Exception as exc:
            return {'error': str(exc)}


# -- 20. git_tool (T2-J) --
# Tier: status/diff/log = read-only  |  commit = write

@register_tool('git_tool')
class GitTool(BaseTool):
    description = (
        'Run git operations in a given repo directory. '
        'Sub-commands: status, diff, log, commit. '
        'status and diff are read-only. log is read-only. commit is a write operation.'
    )
    parameters = [
        {'name': 'subcmd',   'type': 'string',  'required': True,
         'description': 'One of: status | diff | log | commit'},
        {'name': 'repo',     'type': 'string',  'required': False,
         'description': 'Absolute path to git repo. Defaults to /home/yanflare/kdev-deploy.'},
        {'name': 'message',  'type': 'string',  'required': False,
         'description': 'Commit message — required when subcmd is commit.'},
        {'name': 'log_n',    'type': 'integer', 'required': False,
         'description': 'Number of log entries to return (default 10, max 50).'},
    ]

    _DEFAULT_REPO = '/home/yanflare/kdev-deploy'
    _ALLOWED = {'status', 'diff', 'log', 'commit'}

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            subcmd  = p.get('subcmd', '').strip().lower()
            repo    = p.get('repo') or self._DEFAULT_REPO
            message = p.get('message', '').strip()
            log_n   = min(int(p.get('log_n', 10)), 50)
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})

        if subcmd not in self._ALLOWED:
            return json.dumps({'error': f'Unknown subcmd: {subcmd}. Use: status | diff | log | commit'})

        import subprocess as _sp
        from pathlib import Path as _P

        repo_path = _P(repo)
        if not repo_path.is_dir():
            return json.dumps({'error': f'Repo path not found: {repo}'})

        def _run(cmd_list):
            try:
                r = _sp.run(
                    cmd_list,
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                out = (r.stdout + r.stderr)[:4000]
                return json.dumps({'returncode': r.returncode, 'output': out})
            except _sp.TimeoutExpired:
                return json.dumps({'returncode': -1, 'output': 'TIMEOUT: git exceeded 15s'})
            except Exception as exc:
                return json.dumps({'returncode': -1, 'output': f'EXEC_ERROR: {exc}'})

        if subcmd == 'status':
            return _run(['git', 'status', '--short', '--branch'])

        elif subcmd == 'diff':
            return _run(['git', 'diff', 'HEAD'])

        elif subcmd == 'log':
            fmt = '%h %ad %s'
            return _run(['git', 'log', f'--max-count={log_n}',
                         '--date=short', f'--pretty=format:{fmt}'])

        elif subcmd == 'commit':
            if not message:
                return json.dumps({'error': 'commit requires a message parameter'})
            _run(['git', 'add', '-A'])
            return _run(['git', 'commit', '-m', message])

        return json.dumps({'error': 'unreachable'})



# -- 21. process_snapshot (T2-K) --
# Tier: read-only
# Requires: psutil (already in kdev venv)

@register_tool('process_snapshot')
class ProcessSnapshot(BaseTool):
    description = (
        'Return top-N processes by CPU and memory using psutil. '
        'Useful for diagnosing Ollama memory pressure or runaway processes. '
        'Returns two ranked lists: top_cpu and top_mem.'
    )
    parameters = [
        {'name': 'top_n', 'type': 'integer', 'required': False,
         'description': 'Number of processes to return per list (default 10, max 20).'},
    ]

    def call(self, params: str, **kwargs) -> str:
        try:
            p = json.loads(params)
            top_n = min(int(p.get('top_n', 10)), 20)
        except Exception as e:
            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            import psutil as _ps
        except ImportError:
            return json.dumps({'error': 'psutil not installed in venv'})
        try:
            procs = []
            for proc in _ps.process_iter(
                ['pid', 'name', 'cpu_percent', 'memory_info', 'status']
            ):
                try:
                    info = proc.info
                    mem_mb = round(info['memory_info'].rss / 1024 / 1024, 1) if info['memory_info'] else 0
                    procs.append({
                        'pid':     info['pid'],
                        'name':    info['name'],
                        'cpu':     info['cpu_percent'],
                        'mem_mb':  mem_mb,
                        'status':  info['status'],
                    })
                except (_ps.NoSuchProcess, _ps.AccessDenied):
                    continue
            top_cpu = sorted(procs, key=lambda x: x['cpu'],    reverse=True)[:top_n]
            top_mem = sorted(procs, key=lambda x: x['mem_mb'], reverse=True)[:top_n]
            vm = _ps.virtual_memory()
            return json.dumps({
                'total_mem_mb':  round(vm.total  / 1024 / 1024, 1),
                'used_mem_mb':   round(vm.used   / 1024 / 1024, 1),
                'avail_mem_mb':  round(vm.available / 1024 / 1024, 1),
                'mem_pct':       vm.percent,
                'top_cpu':       top_cpu,
                'top_mem':       top_mem,
            })
        except Exception as e:
            return json.dumps({'error': f'PSUTIL_ERROR: {e}'})
KDEV_TOOLS = ['shell_exec', 'file_read', 'file_write', 'skill_save', 'web_search',
              'show_metrics', 'compare_runs', 'memory_ls', 'memory_read', 'memory_write',
              'ssh_exec', 'ssh_exec_background', 'ssh_tail', 'experiment_status',
              'grep_files', 'browser_nav', 'browser_snap', 'browser_action',
              'http_request', 'git_tool', 'process_snapshot']


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

@register_tool('obsidian_write_note')
class ObsidianWriteNote:
    description = 'Write a markdown note into the Obsidian vault. Returns the path of the created file.'
    parameters = [
        {'name': 'title',     'type': 'string', 'description': 'Note title (used in YAML frontmatter and filename slug).', 'required': True},
        {'name': 'content',   'type': 'string', 'description': 'Markdown body of the note.',                               'required': True},
        {'name': 'note_type', 'type': 'string', 'description': 'Subfolder name inside the vault (e.g. skills, logs, dreams). Defaults to "notes".', 'required': False},
        {'name': 'tags',      'type': 'string', 'description': 'Comma-separated tags to add to YAML frontmatter. Optional.', 'required': False},
    ]
    def call(self, params: str, **kwargs) -> str:
        import json, pathlib, datetime, re
        try:
            p = json.loads(params)
            title   = p.get('title',   '').strip()
            content = p.get('content', '').strip()
            if not title:
                return json.dumps({'ok': False, 'error': 'ARGS_PARSE_ERROR: title is required'})
            if not content:
                return json.dumps({'ok': False, 'error': 'ARGS_PARSE_ERROR: content is required'})
        except Exception as e:
            return json.dumps({'ok': False, 'error': f'ARGS_PARSE_ERROR: {e}'})
        try:
            config_path = pathlib.Path.home() / '.kdev' / 'kdev_config.json'
            vault_path  = pathlib.Path(json.loads(config_path.read_text())['obsidian_vault_path'])

            # Accept 'note_type' or 'type' — 9B sometimes passes the shorter form
            raw_type  = (p.get('note_type') or p.get('type') or 'notes').strip() or 'notes'
            note_type = re.sub(r'[^a-zA-Z0-9_\-]', '_', raw_type).strip('_') or 'notes'

            # Accept tags as a list OR a comma-separated string
            raw_tags = p.get('tags', '')
            if isinstance(raw_tags, list):
                tags = [str(t).strip() for t in raw_tags if str(t).strip()]
            else:
                tags = [t.strip() for t in str(raw_tags).split(',') if t.strip()] if raw_tags else []

            ts   = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
            slug = re.sub(r'[^a-zA-Z0-9_\-]', '_', title)[:60].strip('_')
            filename = f'{ts}_{slug}.md'

            out_dir = vault_path / note_type
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / filename

            safe_title   = title.replace('"', '\\"')
            tags_yaml    = ('\ntags:\n' + ''.join(f'  - {t}\n' for t in tags)) if tags else ''
            safe_content = re.sub(r'^---', r'\---', content, flags=re.MULTILINE)

            note = f'---\ntitle: "{safe_title}"\ndate: {ts}{tags_yaml}\n---\n\n{safe_content}\n'

            out_path.write_text(note, encoding='utf-8')
            return json.dumps({'ok': True, 'path': str(out_path)})
        except Exception as e:
            return json.dumps({'ok': False, 'error': f'ERROR: {e}'})
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
