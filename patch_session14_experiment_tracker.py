"""
patch_session14_experiment_tracker.py
Session 14 — ExperimentTracker + experiment_status tool

What this patch does:
  1. Adds on_experiment_launch() — writes /global/experiments/<task_id> to VFS on background launch
  2. Adds on_experiment_complete() — updates the node when .exit file is detected (used by metric loop)
  3. Adds experiment_status tool (tool 14) — single-call experiment overview
  4. Registers 'experiment_status' in KDEV_TOOLS

Run from /home/yanflare/kdev-deploy/:
  python3 patch_session14_experiment_tracker.py
  python3 -c "import kdev_tools; print('import OK')"
  sudo systemctl restart kdev-web
  git add -A && git commit -m "feat: ExperimentTracker + experiment_status tool (Session 14)"
"""

from pathlib import Path
import re

TOOLS_FILE = Path('/home/yanflare/kdev-deploy/kdev_tools.py')

# ── 1. ExperimentTracker functions ────────────────────────────────────────────
# Inserted just before the ssh tools block (before "import subprocess as _sp")

EXPERIMENT_TRACKER_CODE = '\n'.join([
    '',
    '# -- ExperimentTracker (Session 14) --',
    '# Writes experiment metadata to /global/experiments/<task_id> in VFS.',
    '# Uses __global__ session so nodes persist across all future sessions.',
    '',
    '_GLOBAL_SESSION = "__global__"',
    '',
    'def on_experiment_launch(',
    '    task_id: str,',
    '    machine_id: str,',
    '    pid: int,',
    '    command: str,',
    '    log_path: str,',
    '    metric_names: list = None,',
    ') -> None:',
    '    """Write a /global/experiments/<task_id> VFS node on background launch."""',
    '    try:',
    '        import time as _t',
    '        from kdev_memory import vfs_get',
    '        vfs = vfs_get(_GLOBAL_SESSION)',
    '        # Ensure parent directory node exists',
    '        vfs.write(',
    '            "/global/experiments",',
    '            "experiment runs",',
    '            None,',
    '        )',
    '        content_lines = [',
    '            f"task_id:     {task_id}",',
    '            f"machine_id:  {machine_id}",',
    '            f"pid:         {pid}",',
    '            f"command:     {command}",',
    '            f"log_path:    {log_path}",',
    '            f"launched_at: {_t.strftime(\'%Y-%m-%d %H:%M:%S\', _t.localtime())}",',
    '            f"status:      running",',
    '            f"metrics:     {\',\'.join(metric_names) if metric_names else \'none\'}",',
    '        ]',
    '        vfs.write(',
    '            f"/global/experiments/{task_id}",',
    '            f"[running] {command[:60]}",',
    '            "\\n".join(content_lines),',
    '        )',
    '    except Exception as _e:',
    '        import sys',
    '        print(f"[ExperimentTracker] launch write failed: {_e}", file=sys.stderr)',
    '',
    '',
    'def on_experiment_complete(',
    '    task_id: str,',
    '    exit_code: int,',
    '    final_metrics: dict = None,',
    ') -> None:',
    '    """Update the VFS node when the experiment finishes (called by metric loop)."""',
    '    try:',
    '        import time as _t',
    '        from kdev_memory import vfs_get',
    '        vfs = vfs_get(_GLOBAL_SESSION)',
    '        node = vfs.read(f"/global/experiments/{task_id}")',
    '        if node is None:',
    '            return',
    '        existing = node["content"] or ""',
    '        # Replace status line',
    '        status = "done" if exit_code == 0 else f"failed (exit {exit_code})"',
    '        updated = re.sub(r"status:\\s+running", f"status:      {status}", existing)',
    '        # Append completion timestamp',
    '        updated += f"\\nfinished_at: {_t.strftime(\'%Y-%m-%d %H:%M:%S\', _t.localtime())}"',
    '        # Append final metrics if provided',
    '        if final_metrics:',
    '            for k, v in final_metrics.items():',
    '                updated += f"\\nfinal_{k}: {v}"',
    '        status_label = "done" if exit_code == 0 else "failed"',
    '        # Re-read command from existing content for gist',
    '        cmd_match = re.search(r"command:\\s+(.+)", existing)',
    '        cmd_snippet = cmd_match.group(1)[:60] if cmd_match else task_id',
    '        vfs.write(',
    '            f"/global/experiments/{task_id}",',
    '            f"[{status_label}] {cmd_snippet}",',
    '            updated,',
    '        )',
    '    except Exception as _e:',
    '        import sys',
    '        print(f"[ExperimentTracker] complete write failed: {_e}", file=sys.stderr)',
    '',
])

# ── 2. experiment_status tool ─────────────────────────────────────────────────
# Inserted just before the KDEV_TOOLS list

EXPERIMENT_STATUS_TOOL_CODE = '\n'.join([
    '',
    '# -- 14. experiment_status --',
    '',
    '@register_tool(\'experiment_status\')',
    'class ExperimentStatus(BaseTool):',
    '    description = (',
    '        \'List all tracked experiments or read a specific one. \'',
    '        \'Shows status (running/done/failed), command, log_path, and final metrics. \'',
    '        \'Omit task_id to list all experiments. \'',
    '        \'Pair with ssh_tail to get live log output for a running experiment.\'',
    '    )',
    '    parameters = [',
    '        {\'name\': \'task_id\', \'type\': \'string\',',
    '         \'description\': \'Specific task ID to read. Omit to list all.\', \'required\': False},',
    '    ]',
    '',
    '    def call(self, params: str, **kwargs) -> str:',
    '        try:',
    '            p = json.loads(params)',
    '            task_id = p.get(\'task_id\')',
    '        except Exception as e:',
    '            return json.dumps({\'error\': f\'ARGS_PARSE_ERROR: {e}\'})',
    '        try:',
    '            from kdev_memory import vfs_get',
    '            vfs = vfs_get(_GLOBAL_SESSION)',
    '            if task_id:',
    '                node = vfs.read(f"/global/experiments/{task_id}")',
    '                if node is None:',
    '                    return json.dumps({\'error\': f\'No experiment found: {task_id}\'})',
    '                return json.dumps({\'task_id\': task_id, \'content\': node[\'content\'],',
    '                                   \'gist\': node[\'gist\']})',
    '            else:',
    '                tree = vfs.format_tree("/global/experiments")',
    '                return tree or \'No experiments tracked yet.\'',
    '        except Exception as e:',
    '            return json.dumps({\'error\': str(e)})',
    '',
])

# ── 3. Hook on_experiment_launch into ssh_exec_background.call() ──────────────
# Replace the return statement at the end of ssh_exec_background.call()
# Current last lines of the try block:
#   out['note'] = 'Use ssh_tail...'
# return json.dumps(out)

OLD_RETURN = '\n'.join([
    "            if metric_names:",
    "                out['tracking_metrics'] = metric_names",
    "                out['note'] = 'Use ssh_tail to watch log, then show_metrics to query parsed values'",
    "            return json.dumps(out)",
])

NEW_RETURN = '\n'.join([
    "            if metric_names:",
    "                out['tracking_metrics'] = metric_names",
    "                out['note'] = 'Use ssh_tail to watch log, then show_metrics to query parsed values'",
    "            # Session 14 — write experiment node to global VFS",
    "            on_experiment_launch(",
    "                task_id=task_id,",
    "                machine_id=machine_id,",
    "                pid=pid,",
    "                command=command,",
    "                log_path=log_path,",
    "                metric_names=metric_names if metric_names else [],",
    "            )",
    "            return json.dumps(out)",
])

# ── 4. Apply the patch ────────────────────────────────────────────────────────

def apply():
    content = TOOLS_FILE.read_text()

    # 1. Insert ExperimentTracker before SSH tools block
    SSH_TOOLS_MARKER = '# -- SSH tools (multi-machine extension, Helios remote pattern) --'
    if SSH_TOOLS_MARKER not in content:
        print('ERROR: SSH tools marker not found. Is this the right file?')
        return False
    content = content.replace(
        SSH_TOOLS_MARKER,
        EXPERIMENT_TRACKER_CODE + '\n' + SSH_TOOLS_MARKER,
    )
    print('✅ Step 1: ExperimentTracker functions inserted')

    # 2. Insert experiment_status tool before KDEV_TOOLS list
    KDEV_TOOLS_MARKER = "KDEV_TOOLS = ['shell_exec'"
    if KDEV_TOOLS_MARKER not in content:
        print('ERROR: KDEV_TOOLS list marker not found.')
        return False
    content = content.replace(
        KDEV_TOOLS_MARKER,
        EXPERIMENT_STATUS_TOOL_CODE + '\n' + KDEV_TOOLS_MARKER,
    )
    print('✅ Step 2: experiment_status tool inserted')

    # 3. Hook on_experiment_launch into ssh_exec_background
    if OLD_RETURN not in content:
        print('ERROR: ssh_exec_background return block not found. Check indentation.')
        return False
    content = content.replace(OLD_RETURN, NEW_RETURN)
    print('✅ Step 3: on_experiment_launch hooked into ssh_exec_background')

    # 4. Register experiment_status in KDEV_TOOLS list
    OLD_TOOLS_LIST = "'ssh_exec', 'ssh_exec_background', 'ssh_tail']"
    NEW_TOOLS_LIST = "'ssh_exec', 'ssh_exec_background', 'ssh_tail', 'experiment_status']"
    if OLD_TOOLS_LIST not in content:
        print('ERROR: KDEV_TOOLS tail not found.')
        return False
    content = content.replace(OLD_TOOLS_LIST, NEW_TOOLS_LIST)
    print('✅ Step 4: experiment_status registered in KDEV_TOOLS')

    # 5. Write back
    TOOLS_FILE.write_text(content)
    print('\n✅ Patch applied successfully.')
    print('\nNext steps:')
    print('  python3 -c "import kdev_tools; print(\'import OK\')"')
    print('  sudo systemctl restart kdev-web')
    print('  git add -A && git commit -m "feat: ExperimentTracker + experiment_status tool (Session 14)"')
    return True

if __name__ == '__main__':
    apply()
