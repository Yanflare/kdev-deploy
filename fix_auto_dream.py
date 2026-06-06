#!/usr/bin/env python3
import re

with open("/home/yanflare/kdev-deploy/kdev_auto_dream.py", "r", encoding="utf-8") as f:
    content = f.read()

# Force the fine-tuned 9B brain everywhere
content = re.sub(r"huihui_ai/qwen3\.5-abliterated:9b-Claude", "kdev-orchestrator-9b-finetuned-v1:latest", content)
content = re.sub(r'MODEL\s*=\s*["\']huihui_ai/qwen3\.5-abliterated:9b-Claude["\']', 'MODEL = "kdev-orchestrator-9b-finetuned-v1:latest"', content)

# Simplify the massive prompt that was breaking curl
content = re.sub(r'You are KDEV Self-Healing Memory \(autoDream mode.*OUTPUT ONLY THE SINGLE JSON LINE ABOVE', 
                 'You are KDEV Self-Healing Memory (autoDream v3.5). You are powered by the fine-tuned 9B orchestrator. Reply with EXACTLY ONE valid JSON line only.', 
                 content, flags=re.DOTALL)

with open("/home/yanflare/kdev-deploy/kdev_auto_dream.py", "w", encoding="utf-8") as f:
    f.write(content)

print("✅ kdev_auto_dream.py successfully patched to use kdev-orchestrator-9b-finetuned-v1")
print("   (old Claude model removed, prompt simplified)")
