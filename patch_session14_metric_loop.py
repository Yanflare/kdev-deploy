"""
patch_session14_metric_loop.py
Session 14 — On-demand metric parsing in ssh_tail

What this patch does:
  1. ssh_tail.call() now runs parse_metrics() on every log pull
  2. Each parsed point is stored via METRIC_STORE.add()
  3. After parsing, checks for log_path.exit — if found, calls on_experiment_complete()
  4. Returns tail output unchanged — behaviour is identical from the 14b's perspective

Run from /home/yanflare/kdev-deploy/:
  python3 patch_session14_metric_loop.py
  python3 -c "import kdev_tools; print('import OK')"
  sudo systemctl restart kdev-web
  git add -A && git commit -m "feat: on-demand metric parsing in ssh_tail (Session 14)"
"""

from pathlib import Path

TOOLS_FILE = Path('/home/yanflare/kdev-deploy/kdev_tools.py')

# Replace the ssh_tail call() method body
# Old: returns raw tail output only
# New: parses metrics + checks .exit, then returns raw output unchanged

OLD_TAIL_CALL = '\n'.join([
    "    def call(self, params: str, **kwargs) -> str:",
    "        try:",
    "            p = json.loads(params)",
    "            machine_id = p['machine_id']",
    "            log_path   = p['log_path']",
    "            lines      = int(p.get('lines', 50))",
    "        except Exception as e:",
    "            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})",
    "        try:",
    "            result = _run_remote(machine_id, f'tail -n {lines} {_shlex.quote(log_path)}', timeout=10)",
    "            return result['stdout'] or f'(log empty or not found: {log_path})'",
    "        except Exception as e:",
    "            return json.dumps({'error': str(e)})",
])

NEW_TAIL_CALL = '\n'.join([
    "    def call(self, params: str, **kwargs) -> str:",
    "        try:",
    "            p = json.loads(params)",
    "            machine_id   = p['machine_id']",
    "            log_path     = p['log_path']",
    "            lines        = int(p.get('lines', 50))",
    "            metric_names = [n.strip() for n in p['metric_names'].split(',')]  \\",
    "                           if p.get('metric_names') else []",
    "            task_id      = p.get('task_id')",
    "        except Exception as e:",
    "            return json.dumps({'error': f'ARGS_PARSE_ERROR: {e}'})",
    "        try:",
    "            result = _run_remote(machine_id, f'tail -n {lines} {_shlex.quote(log_path)}', timeout=10)",
    "            output = result['stdout'] or ''",
    "            # Session 14 — on-demand metric parsing",
    "            if metric_names and task_id and output:",
    "                points = parse_metrics(output, metric_names)",
    "                for pt in points:",
    "                    METRIC_STORE.add(task_id, pt['metric_name'], pt['value'])",
    "            # Session 14 — check for process completion",
    "            if task_id:",
    "                exit_file = log_path + '.exit'",
    "                try:",
    "                    exit_result = _run_remote(",
    "                        machine_id,",
    "                        f'cat {_shlex.quote(exit_file)} 2>/dev/null',",
    "                        timeout=5,",
    "                    )",
    "                    exit_str = exit_result['stdout'].strip()",
    "                    if exit_str.lstrip('-').isdigit():",
    "                        exit_code = int(exit_str)",
    "                        summary = METRIC_STORE.get_task_summary(task_id)",
    "                        final = {k: v['latest'] for k, v in summary.items()} if summary else None",
    "                        on_experiment_complete(task_id, exit_code, final)",
    "                except Exception:",
    "                    pass  # .exit not found yet — process still running",
    "            return output or f'(log empty or not found: {log_path})'",
    "        except Exception as e:",
    "            return json.dumps({'error': str(e)})",
])

# Also update ssh_tail parameters to expose metric_names and task_id
OLD_TAIL_PARAMS = '\n'.join([
    "    parameters = [",
    "        {'name': 'machine_id', 'type': 'string',",
    "         'description': 'Machine where the log lives.', 'required': True},",
    "        {'name': 'log_path', 'type': 'string',",
    "         'description': 'Absolute path to the log file.', 'required': True},",
    "        {'name': 'lines', 'type': 'string',",
    "         'description': 'Number of lines to return (default 50).', 'required': False},",
    "    ]",
])

NEW_TAIL_PARAMS = '\n'.join([
    "    parameters = [",
    "        {'name': 'machine_id', 'type': 'string',",
    "         'description': 'Machine where the log lives.', 'required': True},",
    "        {'name': 'log_path', 'type': 'string',",
    "         'description': 'Absolute path to the log file.', 'required': True},",
    "        {'name': 'lines', 'type': 'string',",
    "         'description': 'Number of lines to return (default 50).', 'required': False},",
    "        {'name': 'task_id', 'type': 'string',",
    "         'description': 'Task ID from ssh_exec_background. Enables metric parsing and completion detection.', 'required': False},",
    "        {'name': 'metric_names', 'type': 'string',",
    "         'description': 'Comma-separated metric names to parse from log output (e.g. \"loss,accuracy\").', 'required': False},",
    "    ]",
])


def apply():
    content = TOOLS_FILE.read_text()

    # 1. Update ssh_tail parameters
    if OLD_TAIL_PARAMS not in content:
        print('ERROR: ssh_tail parameters block not found. Check indentation.')
        return False
    content = content.replace(OLD_TAIL_PARAMS, NEW_TAIL_PARAMS)
    print('✅ Step 1: ssh_tail parameters updated (task_id + metric_names added)')

    # 2. Update ssh_tail call() method
    if OLD_TAIL_CALL not in content:
        print('ERROR: ssh_tail call() body not found. Check indentation.')
        return False
    content = content.replace(OLD_TAIL_CALL, NEW_TAIL_CALL)
    print('✅ Step 2: ssh_tail call() updated with metric parsing + completion detection')

    # 3. Write back
    TOOLS_FILE.write_text(content)
    print('\n✅ Patch applied successfully.')
    print('\nNext steps:')
    print('  python3 -c "import kdev_tools; print(\'import OK\')"')
    print('  sudo systemctl restart kdev-web')
    print('  git add -A && git commit -m "feat: on-demand metric parsing in ssh_tail (Session 14)"')
    return True


if __name__ == '__main__':
    apply()
