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
        db = _metric_db()
        db.execute(
            'INSERT INTO metric_points (task_id, metric_name, value, ts) VALUES (?,?,?,?)',
            (task_id, metric_name, value, int(_mtime.time() * 1000))
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

KDEV_TOOLS = ['shell_exec', 'file_read', 'file_write', 'skill_save', 'web_search',
              'show_metrics', 'compare_runs', 'memory_ls', 'memory_read', 'memory_write',
              'ssh_exec', 'ssh_exec_background', 'ssh_tail', 'experiment_status']


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
