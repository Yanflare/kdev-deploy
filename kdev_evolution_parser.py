#!/usr/bin/env python3
"""
kdev_evolution_parser.py — Phase 7
Reads completed autoDream cycles from finetune.jsonl,
extracts new_hardware_skill_ideas where confidence > 0.6,
appends to ~/.kdev/proposed_skills.py (staging only),
fires hardware_evolution_proposed trigger to agent_triggers.json.

Does NOT touch kdev_hardware_daemon.py, embodiment_agent.py,
or any live service. Human review required before promotion.
"""

import json
import os
import py_compile
import re
import tempfile
from datetime import datetime
from pathlib import Path

FINETUNE_JSONL   = Path("/home/yanflare/.kdev/finetune.jsonl")
PROPOSED_SKILLS  = Path("/home/yanflare/.kdev/proposed_skills.py")
TRIGGERS_JSON    = Path("/home/yanflare/.kdev/agent_triggers.json")
CONFIDENCE_FLOOR = 0.85
DECLINED_SKILLS  = Path("/home/yanflare/.kdev/declined_skills.txt")
HW_BLACKLIST     = {"distributed", "network_device", "gpio", "servo", "camera", "microphone", "barcode", "haptic", "robotic", "sensor", "spectrometer", "thermal_imager", "vibration", "arm_controller", "voice", "image_processor", "hardware", "physical", "iot", "nvme", "led", "actuator"}
CONCEPT_BLACKLIST = {"rfid", "packet_capture", "network_scanner", "network_packet", "realtime_file", "file_system_watcher", "workspace_watcher", "filesystem_watcher", "file_monitor", "file_watcher", "monitor_file", "semantic_memory", "semantic_tool", "context_window", "parallel_tool_execution", "parallel_session", "parallel_shell", "parallel_computer", "parallel_executor", "parallel_exec", "parallel_reasoning", "parallel_query", "gpu_accelerated", "multi_modal", "direct_file", "web_search_tool", "code_executor", "tool_timeout", "session_correlator", "network_monitor", "cross_session", "timeout_escalator", "environment_context", "external_api_connector"}

# ── helpers ──────────────────────────────────────────────────────────────────

def load_dream_records():
    """Return all finetune records that contain new_hardware_skill_ideas."""
    records = []
    if not FINETUNE_JSONL.exists():
        return records
    with open(FINETUNE_JSONL, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                print(f"  [WARN] line {lineno}: not valid JSON, skipping")
                continue
            # assistant turn may be nested under 'messages' or at top level
            assistant_text = ""
            if "messages" in obj:
                for msg in obj["messages"]:
                    if msg.get("role") == "assistant":
                        assistant_text = msg.get("content", "")
                        break
            elif "output" in obj:
                assistant_text = obj["output"]

            if not assistant_text:
                continue

            # try to parse assistant content as JSON
            try:
                parsed = json.loads(assistant_text)
            except json.JSONDecodeError:
                # sometimes wrapped in markdown fences
                m = re.search(r'\{.*\}', assistant_text, re.DOTALL)
                if not m:
                    continue
                try:
                    parsed = json.loads(m.group())
                except json.JSONDecodeError:
                    continue

            if "new_hardware_skill_ideas" in parsed:
                records.append(parsed)
    return records


def filter_high_confidence(records):
    return [
        r for r in records
        if isinstance(r.get("confidence"), (int, float))
        and r["confidence"] > CONFIDENCE_FLOOR
        and isinstance(r.get("new_hardware_skill_ideas"), list)
        and len(r["new_hardware_skill_ideas"]) > 0
    ]


def load_existing_staging():
    """Return set of skill names already in proposed_skills.py."""
    existing = set()
    if not PROPOSED_SKILLS.exists():
        return existing
    content = PROPOSED_SKILLS.read_text(encoding="utf-8")
    for m in re.finditer(r"# name: (.+)", content):
        existing.add(m.group(1).strip())
    plugins_dir = Path("/home/yanflare/.kdev/plugins")
    if plugins_dir.exists():
        for plugin_file in plugins_dir.glob("*.py"):
            try:
                pcontent = plugin_file.read_text(encoding="utf-8")
                for m in re.finditer(r"def (\w+)\(", pcontent):
                    existing.add(m.group(1).strip())
            except Exception:
                pass
    if Path("/home/yanflare/.kdev/declined_skills.txt").exists():
        for name in Path("/home/yanflare/.kdev/declined_skills.txt").read_text(encoding="utf-8").splitlines():
            existing.add(name.strip())
    return existing


def append_to_staging(skills, confidence, existing_names):
    """Append new skills to proposed_skills.py, skip duplicates."""
    added = []
    lines = []

    if not PROPOSED_SKILLS.exists():
        lines.append("# KDEV — Proposed New Hardware Skills (staging area)")
        lines.append("# Human review required before promotion to live daemon")
        lines.append("# Generated by kdev_evolution_parser.py — do NOT auto-execute")
        lines.append("")

    declined = []
    for skill in skills:
        name = skill.get("name", "").strip()
        if not name or name in existing_names:
            continue
        # keyword blacklist — auto-decline hardware stubs useless on Kiki
        if any(kw in name.lower() for kw in HW_BLACKLIST) or any(kw in name.lower() for kw in CONCEPT_BLACKLIST):
            print(f"  [BLACKLIST] {name!r} matched hardware keyword — skipped")
            continue
        # persistent rejection log — skip manually declined skills
        if DECLINED_SKILLS.exists():
            declined_names = set(DECLINED_SKILLS.read_text(encoding="utf-8").splitlines())
            if name in declined_names:
                print(f"  [DECLINED] {name!r} in declined_skills.txt — skipped")
                continue
        description  = skill.get("description", "")
        code_snippet = skill.get("code_snippet", "")

        # py_compile pre-filter — auto-decline stubs that don't even parse
        if code_snippet.strip():
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".py", delete=False, encoding="utf-8"
                ) as tmp:
                    tmp.write(code_snippet)
                    tmp_path = tmp.name
                py_compile.compile(tmp_path, doraise=True)
            except py_compile.PyCompileError as e:
                print(f"  [AUTO-DECLINE] {name!r} failed py_compile: {e}")
                declined.append(name)
                continue
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        entry = (
            f"\n# --- proposed {datetime.now().isoformat()} | confidence={confidence:.2f} ---\n"
            f"# name: {name}\n"
            f"# description: {description}\n"
            f"# code_snippet:\n"
            f"# {chr(10).join('# ' + l for l in code_snippet.splitlines())}\n"
        )
        lines.append(entry)
        added.append(name)
        existing_names.add(name)
    if declined:
        print(f"  [AUTO-DECLINE] {len(declined)} skill(s) rejected by py_compile: {declined}")

    if added:
        with open(PROPOSED_SKILLS, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"  [STAGING] wrote {len(added)} new skill(s): {added}")
    return added


def fire_trigger(added_names):
    """Append hardware_evolution_proposed trigger — never overwrites existing entries."""
    entries = []
    if TRIGGERS_JSON.exists():
        try:
            entries = json.loads(TRIGGERS_JSON.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                entries = []
        except json.JSONDecodeError:
            entries = []

    entries.append({
        "id": f"trigger-evolution-p7-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "name": "hardware_evolution_proposed",
        "payload": {
            "proposed_skills": added_names,
            "staging_file": str(PROPOSED_SKILLS),
            "action": "human_review_required"
        },
        "fired_at": datetime.now().isoformat(),
        "status": "pending_review"
    })

    # keep last 100 entries only
    entries = entries[-100:]
    TRIGGERS_JSON.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"  [TRIGGER] hardware_evolution_proposed fired — {len(added_names)} skill(s) queued")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"[kdev_evolution_parser] {datetime.now().isoformat()}")
    print(f"  reading: {FINETUNE_JSONL}")

    records = load_dream_records()
    print(f"  dream records with new_hardware_skill_ideas: {len(records)}")

    high = filter_high_confidence(records)
    print(f"  above confidence floor ({CONFIDENCE_FLOOR}): {len(high)}")

    if not high:
        print("  nothing to stage — exiting cleanly")
        return

    existing = load_existing_staging()
    print(f"  already staged: {len(existing)} skill name(s)")

    all_added = []
    for record in high:
        added = append_to_staging(
            record["new_hardware_skill_ideas"],
            record["confidence"],
            existing
        )
        all_added.extend(added)

    if all_added:
        fire_trigger(all_added)
        print(f"  [DONE] {len(all_added)} skill(s) staged for review at {PROPOSED_SKILLS}")
    else:
        print("  all extracted skills already staged — no duplicates written")

if __name__ == "__main__":
    main()
