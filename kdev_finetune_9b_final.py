#!/usr/bin/env python3
"""
KDEV — 9B Orchestrator Fine-Tuning FINAL (Phase 2B)
Bulletproof Modelfile generation — no f-strings, no triple-quote splits.
Author: Claude (Co-Engineer Partner) — 2026-04-01
"""

from pathlib import Path
import subprocess
import json
import random

FINETUNE_PATH = Path("/home/yanflare/.kdev/finetune.jsonl")
BASE_MODEL    = "huihui_ai/qwen3.5-abliterated:9b-Claude"
NEW_MODEL     = "kdev-orchestrator-9b-finetuned-v1"
MODELFILE     = Path("Modelfile.kdev")
NUM_EXAMPLES  = 8


# ── 1. Load records ──────────────────────────────────────────────────────────

def load_records(path):
    records, bad = [], 0
    with open(path, "r", encoding="utf-8") as fh:
        for i, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError:
                bad += 1
                if bad <= 3:
                    print(f"  [SKIP] Bad JSON on line {i}")
    print(f"Loaded {len(records)} clean records | Skipped {bad} bad lines")
    return records


# ── 2. Pick training examples ────────────────────────────────────────────────

def pick_examples(records, n):
    """
    Grab n records that have both a user turn and an assistant turn.
    Falls back gracefully if there are fewer usable records than n.
    """
    usable = [
        r for r in records
        if isinstance(r.get("messages"), list)
        and any(m.get("role") == "user"      for m in r["messages"])
        and any(m.get("role") == "assistant" for m in r["messages"])
    ]
    if not usable:
        print("  [WARN] No records with messages[] format found — skipping examples.")
        return []
    sample = random.sample(usable, min(n, len(usable)))
    print(f"Selected {len(sample)} training examples from {len(usable)} usable records")
    return sample


# ── 3. Build Modelfile lines (NO f-strings on the content block) ─────────────

def build_modelfile_lines(base_model, examples):
    """
    Returns a list of strings (one per line).
    Joining with newlines produces a valid Ollama Modelfile.

    Rule: every value that might contain special chars is kept in a plain
    list literal — no f-string or triple-quote split that could mis-close.
    """
    lines = []

    # -- Header
    lines.append("FROM " + base_model)
    lines.append("")

    # -- Template  (Ollama Go-template syntax, double-braces are literal)
    lines.append("TEMPLATE \"\"\"")
    lines.append("{{ if .System }}{{ .System }}")
    lines.append("{{ end }}{{ .Prompt }}\"\"\"")
    lines.append("")

    # -- System prompt  (written as a plain multi-line SYSTEM block)
    lines.append("SYSTEM \"\"\"")
    lines.append("You are KDEV 9B Orchestrator — the central brain of the full KAIROS + Plugin + VerificationAgent system.")
    lines.append("You operate with MemoryExtractor, AgentTriggers, UltraPlan, and full autonomy.")
    lines.append("You receive structured task requests and respond with clean, structured, actionable plans.")
    lines.append("You coordinate sub-agents, verify results, update memory, and never break the pipeline.")
    lines.append("Always respond in clean, structured, actionable format.")
    lines.append("Phase 2B active. Kingdom mode: ON.")
    lines.append("\"\"\"")
    lines.append("")

    # -- Parameters
    lines.append("PARAMETER num_ctx 32768")
    lines.append("PARAMETER temperature 0.7")
    lines.append("PARAMETER top_p 0.95")
    lines.append("PARAMETER repeat_penalty 1.1")
    lines.append("")

    # -- Training examples (MESSAGE blocks)
    for rec in examples:
        msgs = rec["messages"]
        user_text = next(
            (m["content"] for m in msgs if m.get("role") == "user"), ""
        ).strip()[:400].replace("\n", " ").replace("\r", " ")
        asst_text = next(
            (m["content"] for m in msgs if m.get("role") == "assistant"), ""
        ).strip()[:400].replace("\n", " ").replace("\r", " ")

        if user_text and asst_text:
            lines.append('MESSAGE user """' + user_text.replace('"""', '') + '"""')
            lines.append('MESSAGE assistant """' + asst_text.replace('"""', '') + '"""')
            lines.append("")

    return lines


# ── 4. Write + run + clean ───────────────────────────────────────────────────

def write_modelfile(path, lines):
    content = "\n".join(lines) + "\n"
    path.write_text(content, encoding="utf-8")
    print(f"Modelfile written → {path}  ({len(content)} bytes)")
    # Quick sanity: first line must start with FROM
    first = content.lstrip().split("\n", 1)[0]
    if not first.startswith("FROM "):
        raise ValueError("Modelfile sanity check FAILED — first line is not FROM: " + repr(first))
    print("  Sanity check passed — first line: " + first)


def run_ollama_create(model_name, modelfile_path):
    cmd = ["ollama", "create", model_name, "-f", str(modelfile_path)]
    print("\nRunning: " + " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.stdout:
            print(result.stdout)
        if result.returncode == 0:
            print("\nMODEL CREATED SUCCESSFULLY → " + model_name)
            return True
        else:
            print(f"\nollama create returned code {result.returncode}")
            if result.stderr:
                print("STDERR:\n" + result.stderr)
            return False
    except FileNotFoundError:
        print("ERROR: 'ollama' not found in PATH. Is Ollama installed and running?")
        return False
    except subprocess.TimeoutExpired:
        print("ERROR: ollama create timed out after 600 s")
        return False
    except Exception as exc:
        print("ERROR: " + str(exc))
        return False


# ── 5. Main ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("KDEV 9B Fine-Tuning FINAL (Phase 2B)")
    print("=" * 60)

    records  = load_records(FINETUNE_PATH)
    examples = pick_examples(records, NUM_EXAMPLES)

    lines    = build_modelfile_lines(BASE_MODEL, examples)
    write_modelfile(MODELFILE, lines)

    success = run_ollama_create(NEW_MODEL, MODELFILE)

    # Always clean up
    MODELFILE.unlink(missing_ok=True)
    print("Modelfile.kdev cleaned up.")

    print("\n" + "=" * 60)
    if success:
        print("Phase 2B COMPLETE!")
        print("Next steps:")
        print("  1. ollama list | grep kdev")
        print("  2. Update orchestrator service → model: " + NEW_MODEL)
        print("  3. Restart services → enter Phase 3")
    else:
        print("Phase 2B INCOMPLETE — see errors above.")
        print("Tip: run  ollama list  to confirm the base model name is exact.")
    print("=" * 60)


if __name__ == "__main__":
    main()
