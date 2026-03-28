#!/usr/bin/env python3
"""
kdev_evolve.py — KDEV Self-Improvement Loop
============================================
Borrowed pattern: yoyo-evolve (github.com/yologdev/yoyo-evolve)
Adapted for:     Pure Python + Ollama (no Rust, no GitHub Actions, no cloud)
Model:           huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M
Safe zones only: ~/.kdev/skills/, agent-memory/*.md

Flow:
  1. Read safe-zone files (what can be touched)
  2. Ask 14b to self-assess and write a SESSION_PLAN
  3. For each task in SESSION_PLAN (max 3):
       a. Ask 14b to implement it (one task at a time)
       b. Gate: py_compile check + smoke test
       c. Pass → git commit | Fail → git revert, log failure
  4. Write journal entry to evolve-log.md
  5. Done

Run manually:    python3 /home/yanflare/kdev-deploy/kdev_evolve.py
Run on a cron:   0 3 * * * python3 /home/yanflare/kdev-deploy/kdev_evolve.py >> ~/.kdev/evolve-cron.log 2>&1
"""

import os
import sys
import json
import argparse
import time
import datetime
import subprocess
import py_compile
import tempfile
import textwrap
import re
import requests

# ── Config ────────────────────────────────────────────────────────────────────

DEPLOY_DIR   = "/home/yanflare/kdev-deploy"
KDEV_DIR     = "/home/yanflare/.kdev"
SKILLS_DIR   = os.path.join(KDEV_DIR, "skills")
EVOLVE_LOG   = os.path.join(KDEV_DIR, "evolve-log.md")
PLAN_FILE       = "/tmp/kdev_session_plan.md"
REFLECT_QUEUE   = os.path.join(KDEV_DIR, "reflect-queue.txt")
EVENTS_LOG      = os.path.join(KDEV_DIR, "events.jsonl")
HOP_THRESHOLD   = 10   # runs with >= this many hops go into reflect queue
OLLAMA_URL   = "http://localhost:11434/api/generate"
MODEL        = "huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M"
MAX_TASKS    = 3          # max tasks per session (14b hallucinates on long plans)
PLAN_TIMEOUT = 120        # seconds for planning call
IMPL_TIMEOUT = 180        # seconds per implementation call
OLLAMA_RETRY = 2          # retries on Ollama connection failure

# Protected — the evolve loop must NEVER touch these
PROTECTED = [
    "kdev_web.py",
    "kdev_memory.py",
    "skills.py",
    "kdev.py",
    "kdev_web.py.bak",
    "install.sh",
    "requirements.txt",
]

# Safe zones — only these may be proposed for editing
SAFE_ZONE_FILES = [
    os.path.join(DEPLOY_DIR, "agent-memory", "workspace-agent.md"),
    os.path.join(DEPLOY_DIR, "agent-memory", "user-agent.md"),
]
SAFE_ZONE_DIRS = [
    SKILLS_DIR,
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def today() -> str:
    return datetime.datetime.now().strftime("%Y%m%d")

def log(msg: str):
    print(f"[kdev-evolve] {msg}", flush=True)

def git(cmd: str) -> tuple[int, str]:
    result = subprocess.run(
        f"cd {DEPLOY_DIR} && {cmd}",
        shell=True, capture_output=True, text=True
    )
    return result.returncode, (result.stdout + result.stderr).strip()

def current_sha() -> str:
    _, sha = git("git rev-parse HEAD")
    return sha.strip()

def revert_to(sha: str):
    git(f"git reset --hard {sha}")
    git("git clean -fd")

def py_compile_check(filepath: str) -> tuple[bool, str]:
    """Return (ok, error_msg). Only meaningful for .py files."""
    if not filepath.endswith(".py"):
        return True, ""
    try:
        py_compile.compile(filepath, doraise=True)
        return True, ""
    except py_compile.PyCompileError as e:
        return False, str(e)

def smoke_test() -> tuple[bool, str]:
    """Import kdev_memory and call get_memory_stats(). Proves core is intact."""
    result = subprocess.run(
        [
            "/home/yanflare/.kdev-venv/bin/python3", "-c",
            "import sys; sys.path.insert(0, '/home/yanflare/kdev-deploy'); "
            "from kdev_memory import get_memory_stats; s = get_memory_stats(); "
            "assert isinstance(s, dict), 'bad stats'; print('smoke ok')"
        ],
        capture_output=True, text=True, timeout=15
    )
    ok = result.returncode == 0 and "smoke ok" in result.stdout
    return ok, (result.stdout + result.stderr).strip()

def read_file_safe(path: str, max_chars: int = 4000) -> str:
    try:
        with open(path) as f:
            content = f.read(max_chars)
        if len(content) == max_chars:
            content += "\n... [truncated]"
        return content
    except Exception as e:
        return f"[could not read: {e}]"

def read_safe_zone() -> str:
    """Collect the content of all safe-zone files for context injection."""
    parts = []
    for path in SAFE_ZONE_FILES:
        rel = os.path.relpath(path, DEPLOY_DIR)
        parts.append(f"### {rel}\n{read_file_safe(path)}")

    # Sample up to 5 recent skills from ~/.kdev/skills/
    skill_files = []
    for root, _, files in os.walk(SKILLS_DIR):
        for f in files:
            if f.endswith(".md"):
                skill_files.append(os.path.join(root, f))
    skill_files.sort(key=os.path.getmtime, reverse=True)
    for sf in skill_files[:5]:
        rel = os.path.relpath(sf, KDEV_DIR)
        parts.append(f"### skills/{rel} (recent)\n{read_file_safe(sf, 800)}")

    # Inject full list of auto-generated dated skill filenames for topic-cluster dedup (Session 38)
    dated_skills = sorted(
        f.name for f in os.scandir(SKILLS_DIR)
        if f.is_file() and re.match(r"\d{8}-", f.name) and f.name.endswith(".md")
    )
    if dated_skills:
        TRIM = 300
        older = dated_skills[:-TRIM] if len(dated_skills) > TRIM else []
        recent = dated_skills[-TRIM:] if len(dated_skills) > TRIM else dated_skills
        skill_name_block = "### AUTO-GENERATED SKILL FILENAMES (topic dedup — DO NOT REPEAT THESE TOPICS):\n"
        if older:
            # Extract topic words from older filenames (strip date prefix)
            older_topics = sorted(set(
                re.sub(r"^\d{8}-", "", f).replace(".md", "").replace("-", " ")
                for f in older
            ))
            skill_name_block += f"(Older {len(older)} skills summarised — topics covered: "
            skill_name_block += ", ".join(older_topics[:80])
            if len(older_topics) > 80:
                skill_name_block += f" ... and {len(older_topics) - 80} more"
            skill_name_block += ")\n\n"
        skill_name_block += "Recent 300 filenames (full list):\n"
        skill_name_block += "\n".join(recent)
        parts.append(skill_name_block)
    return "\n\n---\n\n".join(parts)

def read_evolve_log(last_n: int = 5) -> str:
    """Return the last N journal entries from evolve-log.md."""
    if not os.path.exists(EVOLVE_LOG):
        return "(no previous evolve sessions)"
    with open(EVOLVE_LOG) as f:
        content = f.read()
    # Entries are separated by "## Session"
    entries = re.split(r"(?=## Session)", content)
    recent = [e.strip() for e in entries if e.strip()][-last_n:]
    return "\n\n".join(recent) if recent else "(no entries yet)"

def ollama_call(prompt: str, timeout: int = 120) -> str:
    """Send a prompt to Ollama, return the full response text."""
    for attempt in range(OLLAMA_RETRY + 1):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={"model": MODEL, "prompt": prompt, "stream": False},
                timeout=timeout
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except requests.exceptions.Timeout:
            log(f"Ollama timeout (attempt {attempt+1}/{OLLAMA_RETRY+1})")
            if attempt == OLLAMA_RETRY:
                raise
            time.sleep(5)
        except Exception as e:
            log(f"Ollama error: {e}")
            raise

def parse_plan(plan_text: str) -> list[dict]:
    """
    Extract tasks from SESSION_PLAN.md text.
    Returns list of {"title": str, "files": str, "description": str}
    """
    tasks = []
    # Match blocks: ### Task N: title ... until next ### Task or end
    blocks = re.split(r"(?=### Task \d+:)", plan_text)
    for block in blocks:
        m = re.match(r"### Task \d+:\s*(.+)", block)
        if not m:
            continue
        title = m.group(1).strip()
        files_m = re.search(r"Files:\s*(.+)", block)
        desc_m  = re.search(r"Description:\s*([\s\S]+?)(?=\n###|$)", block)
        files = files_m.group(1).strip() if files_m else "unknown"
        desc  = desc_m.group(1).strip()  if desc_m  else block.strip()
        tasks.append({"title": title, "files": files, "description": desc})
    return tasks[:MAX_TASKS]

def filter_duplicate_tasks(tasks: list[dict]) -> list[dict]:
    """
    Drop any proposed task whose skill topic is semantically equivalent to an
    existing dated skill filename. Uses normalised word-overlap (Jaccard) scoring.
    A task is dropped if overlap_score >= DEDUP_THRESHOLD.
    """
    DEDUP_THRESHOLD = 0.5

    existing_topics = []
    try:
        for f in os.scandir(SKILLS_DIR):
            if f.is_file() and re.match(r"\d{8}-", f.name) and f.name.endswith(".md"):
                topic = re.sub(r"^\d{8}-", "", f.name).replace(".md", "")
                words = set(topic.lower().replace("-", " ").split())
                existing_topics.append(words)
    except Exception:
        return tasks  # if scan fails, don't block anything

    accepted = []
    for task in tasks:
        files_str = task.get("files", "")
        fname = __import__("os").path.basename(
            re.split(r"[,\s]+", files_str.strip())[0].strip("'\"[]")
        )
        topic_raw = re.sub(r"^\d{8}-", "", fname).replace(".md", "")
        proposed_words = set(topic_raw.lower().replace("-", " ").split())

        if not proposed_words:
            accepted.append(task)
            continue

        is_dup = False
        for existing_words in existing_topics:
            if not existing_words:
                continue
            union = proposed_words | existing_words
            if not union:
                continue
            overlap = len(proposed_words & existing_words) / len(union)
            if overlap >= DEDUP_THRESHOLD:
                log(f"  [dedup] DROPPED '{task['title']}' — topic overlap {overlap:.2f} with existing skill")
                is_dup = True
                break

        if not is_dup:
            accepted.append(task)

    dropped = len(tasks) - len(accepted)
    if dropped:
        log(f"  [dedup] {dropped} task(s) filtered by Python dedup gate. {len(accepted)} remaining.")
    return accepted


def is_safe(files_str: str) -> tuple[bool, str]:
    """
    Check that every file mentioned in the task is within the safe zone.
    Returns (ok, reason).
    """
    # Collect all token-like paths from the files string
    tokens = re.split(r"[,\s]+", files_str)
    for token in tokens:
        token = token.strip().strip("'\"")
        if not token:
            continue
        # Reject anything that is a protected filename
        basename = os.path.basename(token)
        if basename in PROTECTED:
            return False, f"Protected file: {token}"
        # Accept if it's under a safe zone dir
        abs_token = token if token.startswith("/") else os.path.join(DEPLOY_DIR, token)
        in_safe = any(abs_token.startswith(d) for d in SAFE_ZONE_DIRS)
        in_safe_file = abs_token in [os.path.abspath(p) for p in SAFE_ZONE_FILES]
        if not in_safe and not in_safe_file:
            # Allow agent-memory/ and skills/ relative paths
            if not any(s in token for s in ["agent-memory/", "skills/", ".kdev/skills"]):
                return False, f"Outside safe zone: {token}"
    return True, ""

def append_journal(session_dt: str, tasks_attempted: int, tasks_ok: int, notes: str):
    header = f"## Session {session_dt}\n"
    body   = (
        f"- Tasks attempted: {tasks_attempted}\n"
        f"- Tasks committed: {tasks_ok}\n"
        f"- Notes: {notes}\n"
    )
    entry = header + body + "\n"
    with open(EVOLVE_LOG, "a") as f:
        f.write(entry)
    log(f"Journal written to {EVOLVE_LOG}")

# ── Phase A: Planning ─────────────────────────────────────────────────────────

def run_planning(safe_zone_content: str, past_log: str, hint: str = '') -> str:
    today_str = today()
    hint_block = (
        '## Priority topic from reflection queue:' + chr(10) +
        hint + chr(10) +
        'Strongly prefer creating a skill for this topic above all others.' + chr(10)
    ) if hint else ''
    prompt = textwrap.dedent(f"""
    {hint_block}You are KDEV's self-improvement agent running on Kiki (local Linux PC).
    Today's date: {today_str}
    Your job: read the safe-zone files below and write a SESSION_PLAN.md.

    ## What you CAN touch (safe zone only):
    - ~/.kdev/skills/*.md  (add or improve skill files)
    - agent-memory/workspace-agent.md (improve workspace behaviour rules)
    - agent-memory/user-agent.md (improve user profile)

    ## What you must NEVER touch:
    kdev_web.py, kdev_memory.py, skills.py, kdev.py, install.sh, requirements.txt

    ## Safe-zone file contents:
    {safe_zone_content}

    ## Past evolve sessions (last 10 — READ CAREFULLY BEFORE PLANNING):
    {past_log}

    ## BEFORE writing the plan, extract from the past sessions above:
    ## - Every skill filename already created (YYYYMMDD-*.md entries)
    ## - Every agent-memory section already edited
    ## You MUST NOT propose any task that touches a file or topic already listed there.

    ## Your task:
    Write SESSION_PLAN.md with EXACTLY this format (max {MAX_TASKS} tasks):

    ## Session Plan

    ### Task 1: [title]
    Files: [exact relative path(s) — safe zone only]
    Description: [what to do, specific and actionable]

    ### Task 2: [title]
    Files: [exact relative path(s)]
    Description: [what to do]

    Rules:
    - Each task must only touch files in the safe zone listed above.
    - Each task must be small enough to complete in one focused edit.
    - HARD RULE: Do NOT propose any task whose file or topic already appears in past sessions.
    - HARD RULE: The safe-zone context above contains a complete list of AUTO-GENERATED SKILL FILENAMES.
      Before proposing any skill, strip the date prefix and compare the topic words against every
      entry in that list. If the topic is semantically equivalent (same tool, same concept, same
      command) — even if the exact title differs — DO NOT propose it. Examples of forbidden
      duplicates: vmstat-monitoring / vmstat-monitoring-function / vmstat-summary are all the same.
      nethogs-advanced / nethogs-monitoring-function are the same. Choose a genuinely different topic.
    - If a skill topic was attempted but failed (reverted), that topic is still off-limits.
    - STRONGLY PREFER creating new skill files in ~/.kdev/skills/ over editing agent-memory files.
    - Only propose editing agent-memory files if you have a genuinely new, specific improvement.
    - When creating a skill, choose a topic NOT already in the skill inventory above.
    - Skill filenames MUST start with today's date in YYYYMMDD format, e.g. {today_str}-my-skill-name.md
    - Output ONLY the SESSION_PLAN.md content. No preamble, no explanation.
    """).strip()

    log("Phase A: Asking 14b to plan...")
    return ollama_call(prompt, timeout=PLAN_TIMEOUT)

# ── Phase B: Implementation ───────────────────────────────────────────────────

def run_task(task: dict, task_num: int, session_dt: str) -> str:
    """Ask 14b to implement one task. Returns the raw response (file content or diff)."""
    # Read the current content of the target file(s) for context
    files_context = ""
    for token in re.split(r"[,\s]+", task["files"]):
        token = token.strip().strip("'\"")
        if not token:
            continue
        # Resolve path
        if token.startswith("/"):
            abs_path = token
        elif token.startswith("~/.kdev"):
            abs_path = token.replace("~", "/home/yanflare")
        else:
            abs_path = os.path.join(DEPLOY_DIR, token)
        files_context += f"\n### Current content of {token}:\n{read_file_safe(abs_path)}\n"

    prompt = textwrap.dedent(f"""
    You are KDEV's self-improvement agent. Implement exactly ONE task.

    ## Task {task_num}: {task["title"]}
    Files: {task["files"]}
    Description: {task["description"]}

    ## Current file content(s):
    {files_context}

    ## Instructions:
    - Output the COMPLETE new content of the file(s) to be written.
    - If multiple files, separate them with: === FILE: <path> ===
    - Output ONLY the file content(s). No explanation, no markdown fences.
    - Keep changes minimal and focused on the task description.
    - Do not touch any file not listed in "Files" above.
    ## SKILL FILE QUALITY RULES (mandatory):
    - NEVER invent modules, functions, or tool names that do not exist in KDEV.
    - NEVER write a skill whose content is just a description of a feature to build.
    - NEVER reference mcp_toolkit, nautilus, or any external system not in KDEV tool registry.
    - EVERY skill must contain at least ONE concrete example using a real KDEV tool:
      shell_exec, file_read, file_write, web_search, memory_ls, memory_read,
      memory_write, ssh_exec, ssh_exec_background, ssh_tail, experiment_status,
      compare_runs, metric_poller, grep_files, browser_nav, browser_snap,
      browser_action, http_request, git_tool, process_snapshot.
    - Use ONLY tool names from the list above. Any other snake_case name will be
      rejected by the quality gate.
    - Skills must be specific to KDEV architecture. Generic tips are NOT skills.
    ## SKILL FILE FORMAT (required structure):
    ---
    title: [short descriptive title]
    tags: [2-4 relevant tags]
    complexity: [low|medium|high]
    summary: [one sentence: what problem this skill solves]
    ---
    ## When to use
    [1-3 sentences: exact situation where this skill applies]
    ## Approach
    [2-5 sentences: concrete strategy referencing real KDEV tools by name]
    ## Example
    [A real working example using actual KDEV tool calls or shell commands]
    ## Pitfalls
    [1-3 specific failure modes based on known KDEV behaviour]
    """).strip()

    log(f"  Phase B Task {task_num}: Asking 14b to implement '{task['title']}'...")
    return ollama_call(prompt, timeout=IMPL_TIMEOUT)

def apply_task_output(task: dict, response: str) -> list[tuple[str, str]]:
    """
    Parse the model response and return list of (abs_path, new_content) pairs.
    Handles single-file and multi-file (=== FILE: path ===) responses.
    """
    results = []

    # Multi-file format
    if "=== FILE:" in response:
        blocks = re.split(r"=== FILE:\s*(.+?)\s*===", response)
        # blocks[0] is pre-content (ignore), then alternating path, content
        it = iter(blocks[1:])
        for path_token, content in zip(it, it):
            path_token = path_token.strip()
            abs_path = resolve_path(path_token)
            results.append((abs_path, content.strip()))
    else:
        # Single file — use the first file listed in task["files"]
        tokens = [t.strip().strip("'\"") for t in re.split(r"[,\s]+", task["files"]) if t.strip()]
        if tokens:
            abs_path = resolve_path(tokens[0])
            results.append((abs_path, response.strip()))

    return results

def resolve_path(token: str) -> str:
    if token.startswith("/"):
        return token
    if token.startswith("~/.kdev"):
        return token.replace("~", "/home/yanflare")
    return os.path.join(DEPLOY_DIR, token)

# ── Verification gate ─────────────────────────────────────────────────────────

# T1-A applied
KDEV_REAL_TOOLS = [
    "shell_exec", "file_read", "file_write", "web_search",
    "memory_ls", "memory_read", "memory_write",
    "ssh_exec", "ssh_exec_background", "ssh_tail",
    "experiment_status", "compare_runs",
    "metric_poller", "grep_files",
    "browser_nav", "browser_snap", "browser_action",
    "http_request", "git_tool", "process_snapshot",
]

# Candidate tool-name pattern: word_word or word_word_word (snake_case identifiers)
# used in quality gate to catch references to non-existent tools
_TOOL_NAME_RE = re.compile(r'\b([a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)+)\b')

BOILERPLATE_PHRASES = [
    "mcp_toolkit", "nautilus", "is_available()",
    "import mcp_", "adjust according to", "actual implementation",
    "should be adjusted", "facilitating targeted", "key features:",
    "enhanced data analysis",
]

def quality_gate_skill(abs_path: str, content: str) -> tuple[bool, str]:
    """Reject skill files that are boilerplate or hallucinated."""
    if not abs_path.endswith(".md"):
        return True, "ok"
    if ".kdev/skills" not in abs_path and "skills/" not in abs_path:
        return True, "ok"
    if len(content.strip()) < 400:
        return False, "Skill too short -- likely boilerplate"
    has_tool = any(tool in content for tool in KDEV_REAL_TOOLS)
    has_shell = any(kw in content for kw in ["```bash", "```python", "shell_exec"])
    if not has_tool and not has_shell:
        return False, "Skill has no real KDEV tool reference or code example"
    content_lower = content.lower()
    for phrase in BOILERPLATE_PHRASES:
        if phrase.lower() in content_lower:
            return False, "Skill contains boilerplate phrase: " + phrase
    # T1-A: reject skills that reference snake_case names that look like tool
    # calls but are not in the real tool registry
    candidate_names = set(_TOOL_NAME_RE.findall(content))
    # Only check tokens that plausibly look like tool invocations:
    # present in a code block line, or immediately followed by '(' or a space+path
    invocation_re = re.compile(
        r'(?:^|[\s`])([a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)+)\s*(?:\(|\s+[/~"\'\w])',
        re.MULTILINE
    )
    invoked = set(invocation_re.findall(content))
    # Filter: only flag names that look like kdev tools (contain underscore,
    # all lowercase, not a common python builtin or markdown word)
    COMMON_NON_TOOLS = {
        "for_loop", "if_else", "try_except", "def_run", "make_sure",
        "up_to", "set_up", "based_on", "such_as", "so_that",
        "in_the", "of_the", "to_the", "on_the", "at_the",
    }
    hallucinated = [
        name for name in invoked
        if name not in KDEV_REAL_TOOLS
        and name not in COMMON_NON_TOOLS
        and len(name) >= 6
        and name.count('_') >= 1
    ]
    if hallucinated:
        return False, "Skill references unknown tool(s): " + ", ".join(sorted(hallucinated))
    return True, "ok"

def verify_task(written_files: list[tuple[str, str]]) -> tuple[bool, str]:
    """
    Gate 1: skill quality check on .md skill files.
    Gate 2: py_compile on any .py files written.
    Gate 3: smoke test.
    Returns (ok, reason).
    """
    for abs_path, content in written_files:
        ok, err = quality_gate_skill(abs_path, content)
        if not ok:
            return False, "Skill quality gate failed: " + err
        ok, err = py_compile_check(abs_path)
        if not ok:
            return False, "py_compile failed on " + abs_path + ": " + err
    ok, msg = smoke_test()
    if not ok:
        return False, "Smoke test failed: " + msg
    return True, "ok"
# ── Main loop ─────────────────────────────────────────────────────────────────


# ── Reflect mode ─────────────────────────────────────────────────────────────

def run_reflect():
    """Scan events.jsonl for high-hop or error runs and update reflect-queue.txt."""
    if not os.path.exists(EVENTS_LOG):
        log("[reflect] events.jsonl not found — skipping")
        return
    candidates = []
    try:
        with open(EVENTS_LOG, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        log(f"[reflect] Could not read events.jsonl: {e}")
        return
    for raw in lines[-50:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            ev = json.loads(raw)
        except Exception:
            continue
        hops = ev.get('hops', 0)
        if hops >= HOP_THRESHOLD:
            task = ev.get('message', '').strip()
            if task and len(task) > 10:
                candidates.append(task[:120])
    if not candidates:
        log("[reflect] No high-hop or error runs found — queue unchanged")
        return
    existing = set()
    if os.path.exists(REFLECT_QUEUE):
        with open(REFLECT_QUEUE, 'r', encoding='utf-8') as f:
            existing = set(l.strip() for l in f if l.strip())
    new_topics = [c for c in candidates if c not in existing]
    if not new_topics:
        log("[reflect] All candidates already in queue")
        return
    with open(REFLECT_QUEUE, 'a', encoding='utf-8') as f:
        for topic in new_topics:
            f.write(topic + chr(10))
    log(f"[reflect] Added {len(new_topics)} topic(s) to reflect-queue.txt")
def main():
    parser = argparse.ArgumentParser(description='KDEV Self-Improvement Loop')
    parser.add_argument('--hint', type=str, default='',
                        help='Priority topic to prepend to Phase A prompt')
    parser.add_argument('--reflect-queue', action='store_true',
                        help='Run reflect-only mode: update queue then exit')
    args = parser.parse_args()

    # Reflect-only mode: update reflect-queue.txt and exit
    if args.reflect_queue:
        run_reflect()
        sys.exit(0)

    session_dt = now()
    log(f"=== KDEV Evolve Session {session_dt} ===")
    log(f"Model: {MODEL}")
    log(f"Deploy dir: {DEPLOY_DIR}")
    log(f"Safe zones: {SAFE_ZONE_DIRS + SAFE_ZONE_FILES}")

    # Verify git is ready
    rc, out = git("git status --short")
    if rc != 0:
        log(f"FATAL: git not available in {DEPLOY_DIR}: {out}")
        sys.exit(1)

    # Verify Ollama is up
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        r.raise_for_status()
        log("Ollama: reachable")
    except Exception as e:
        log(f"FATAL: Ollama not reachable: {e}")
        sys.exit(1)

    # Verify smoke test passes BEFORE we touch anything
    ok, msg = smoke_test()
    if not ok:
        log(f"FATAL: Pre-session smoke test failed — aborting to avoid corrupting a broken state: {msg}")
        sys.exit(1)
    log("Pre-session smoke test: OK")

    # Read context
    safe_zone_content = read_safe_zone()
    past_log = read_evolve_log(last_n=10)  # T1-B applied

    # ── Phase A: Plan ──────────────────────────────────────────────────────────
    try:
        plan_text = run_planning(safe_zone_content, past_log, hint=args.hint)
    except Exception as e:
        log(f"Planning failed: {e}")
        append_journal(session_dt, 0, 0, f"Planning phase failed: {e}")
        sys.exit(1)

    # Save plan for inspection
    with open(PLAN_FILE, "w") as f:
        f.write(plan_text)
    log(f"Plan saved to {PLAN_FILE}")

    tasks = parse_plan(plan_text)
    if not tasks:
        log("No tasks parsed from plan. Exiting.")
        append_journal(session_dt, 0, 0, "Planner produced no parseable tasks.")
        os.remove(PLAN_FILE)
        return

    tasks = filter_duplicate_tasks(tasks)
    if not tasks:
        log("All proposed tasks were duplicates — nothing to do this session.")
        append_journal(session_dt, 0, 0, "All tasks filtered by dedup gate.")
        return
    log(f"Tasks planned: {len(tasks)}")
    for i, t in enumerate(tasks, 1):
        log(f"  Task {i}: {t['title']} | Files: {t['files']}")

    # ── Phase B: Implement ────────────────────────────────────────────────────
    tasks_attempted = 0
    tasks_ok = 0
    notes_parts = []

    for task_num, task in enumerate(tasks, 1):
        tasks_attempted += 1
        pre_sha = current_sha()

        # Safety check before touching anything
        safe, reason = is_safe(task["files"])
        if not safe:
            msg = f"Task {task_num} BLOCKED (unsafe files): {reason}"
            log(f"  {msg}")
            notes_parts.append(msg)
            continue

        # Implement
        try:
            response = run_task(task, task_num, session_dt)
        except Exception as e:
            msg = f"Task {task_num} implementation call failed: {e}"
            log(f"  {msg}")
            notes_parts.append(msg)
            continue

        # Parse and write files
        try:
            written = apply_task_output(task, response)
        except Exception as e:
            msg = f"Task {task_num} output parsing failed: {e}"
            log(f"  {msg}")
            notes_parts.append(msg)
            continue

        if not written:
            msg = f"Task {task_num} produced no files to write"
            log(f"  {msg}")
            notes_parts.append(msg)
            continue

        # Write files to disk
        write_errors = []
        for abs_path, content in written:
            try:
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, "w") as f:
                    f.write(content)
                log(f"  Wrote: {abs_path}")
            except Exception as e:
                write_errors.append(f"{abs_path}: {e}")

        if write_errors:
            msg = f"Task {task_num} write errors: {'; '.join(write_errors)}"
            log(f"  {msg}")
            revert_to(pre_sha)
            notes_parts.append(msg + " — reverted")
            continue

        # Verification gate
        ok, reason = verify_task(written)
        if not ok:
            log(f"  Task {task_num} FAILED verification: {reason}")
            log(f"  Reverting to {pre_sha[:8]}...")
            revert_to(pre_sha)
            notes_parts.append(f"Task {task_num} '{task['title']}' reverted: {reason}")
            continue

        # Commit
        commit_msg = f"evolve {session_dt}: Task {task_num} - {task['title']}"
        rc, out = git(f"git add -A && git commit -m '{commit_msg}'")
        if rc != 0:
            if "nothing to commit" in out:
                # Skill files written outside repo -- not a failure
                tasks_ok += 1
                log(f"  Task {task_num} WRITTEN (outside repo): {task['title']}")
                notes_parts.append(f"Task {task_num} '{task['title']}' written OK (skill file)")
                continue
            msg = f"Task {task_num} git commit failed: {out}"
            log(f"  {msg}")
            revert_to(pre_sha)
            notes_parts.append(msg + " — reverted")
            continue

        tasks_ok += 1
        log(f"  Task {task_num} COMMITTED: {task['title']}")
        notes_parts.append(f"Task {task_num} '{task['title']}' committed OK")

    # ── Cleanup ────────────────────────────────────────────────────────────────
    if os.path.exists(PLAN_FILE):
        os.remove(PLAN_FILE)

    # ── Journal ────────────────────────────────────────────────────────────────
    notes = " | ".join(notes_parts) if notes_parts else "All tasks completed cleanly"
    append_journal(session_dt, tasks_attempted, tasks_ok, notes)

    log(f"=== Session complete: {tasks_ok}/{tasks_attempted} tasks committed ===")

if __name__ == "__main__":
    main()
