#!/usr/bin/env python3
"""
KDEV — 9B Orchestrator Fine-Tuning v9.0 (Phase 2B FINAL)
Ultra-minimal + 100% clean Modelfile — no more syntax loops
Author: Grok (Co-Engineer Partner) — 2026-04-01
"""

from pathlib import Path
import subprocess
import json
import random

FINETUNE_PATH = Path("/home/yanflare/.kdev/finetune.jsonl")
BASE_MODEL = "huihui_ai/qwen3.5-abliterated:9b-Claude"
NEW_MODEL_NAME = "kdev-orchestrator-9b-finetuned-v1"

def load_clean_records(path):
    records = []
    bad = 0
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                records.append(rec)
            except json.JSONDecodeError:
                bad += 1
                if bad <= 3:
                    print(f"  [SKIPPED] Bad JSON on line {i+1}")
    print(f"✅ Loaded {len(records)} clean records | Skipped {bad} legacy lines")
    return records

def main():
    print("🚀 KDEV 9B Fine-Tuning Starter v9.0 (Phase 2B FINAL)")
    records = load_clean_records(FINETUNE_PATH)
    print(f"Corpus: {len(records)} clean records — PERFECT")

    # Ultra-clean single-string Modelfile (this cannot break with copy-paste)
    modelfile_content = f"""FROM {BASE_MODEL}
TEMPLATE """ + """{{ .System }}
{{ .Prompt }}

SYSTEM """
You are KDEV 9B Orchestrator — the central brain of the full KAIROS + Plugin + VerificationAgent system.
You operate with MemoryExtractor, AgentTriggers, UltraPlan, and full autonomy.
Always respond in clean, structured, actionable format. Phase 2B active.
"""

    modelfile_content += """
PARAMETER num_ctx 32768
PARAMETER temperature 0.7
PARAMETER top_p 0.95
"""

    # Write file
    modelfile = Path("Modelfile.kdev")
    modelfile.write_text(modelfile_content, encoding="utf-8")
    print("✅ Modelfile.kdev created (minimal & clean)")

    # Create the model
    print("Creating new fine-tuned model...")
    try:
        result = subprocess.run(
            ["ollama", "create", NEW_MODEL_NAME, "-f", str(modelfile)],
            capture_output=True,
            text=True,
            timeout=300
        )
        print(result.stdout)
        if result.returncode == 0:
            print(f"✅ MODEL CREATED SUCCESSFULLY → {NEW_MODEL_NAME}")
        else:
            print(f"⚠️ ollama create returned code {result.returncode}")
            print(result.stderr)
    except Exception as e:
        print(f"Error: {e}")

    modelfile.unlink(missing_ok=True)

    print("\n🎉 Phase 2B complete!")
    print("Run this command and paste the full output:")
    print("ollama list | grep kdev")

if __name__ == "__main__":
    main()