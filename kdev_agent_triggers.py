#!/usr/bin/env python3
"""
KDEV — AGENT_TRIGGERS_REMOTE + Full Skills Injection v1.0
Ported & upgraded from paoloanzn/free-code (AGENT_TRIGGERS / AGENT_TRIGGERS_REMOTE) + instructkr/claw-code (plugin pipeline)
Author: Grok (Co-Engineer Partner) — 2026-04-01
"""

import json
import time
from pathlib import Path
from datetime import datetime
from kdev_plugin_manager import KDEVPluginManager   # reuse what we already have

class KDEVAgentTriggers:
    def __init__(
        self,
        trigger_file: str = "/home/yanflare/.kdev/agent_triggers.json",
        debug: bool = True
    ):
        self.trigger_file = Path(trigger_file)
        self.debug = debug
        self.plugin_manager = KDEVPluginManager(debug=False)  # silent

        self.trigger_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.trigger_file.exists():
            self.trigger_file.write_text("[]\n")

        if self.debug:
            print(f"[KDEV-TRIGGERS] Remote trigger system initialized | Watching {self.trigger_file}")

    def fire_remote_trigger(self, trigger_name: str, payload: dict = None):
        """AGENT_TRIGGERS_REMOTE — exactly as in the leaked Claude Code"""
        if payload is None:
            payload = {}

        entry = {
            "id": f"trigger-{int(time.time())}",
            "name": trigger_name,
            "payload": payload,
            "fired_at": datetime.now().isoformat(),
            "status": "fired"
        }

        # Append to trigger file (watched by future KAIROS hooks)
        try:
            data = json.loads(self.trigger_file.read_text() or "[]")
            data.append(entry)
            data = data[-100:]  # keep last 100
            self.trigger_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            print(f"[KDEV-TRIGGERS] Failed to write trigger: {e}")

        # Also fire through the plugin system
        self.plugin_manager.trigger_agent(trigger_name, payload)

        if self.debug:
            print(f"[KDEV-TRIGGERS] 🔥 Remote trigger FIRED: {trigger_name} | Payload: {payload}")

    def check_for_pending_triggers(self):
        """Future-proof: can be called from KAIROS loop"""
        try:
            data = json.loads(self.trigger_file.read_text() or "[]")
            return [t for t in data if t.get("status") == "pending"]
        except:
            return []

# ─────────────────────────────────────────────────────────────
# QUICK TEST + AUTO-REGISTER EXAMPLE SKILLS
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    triggers = KDEVAgentTriggers()
    triggers.fire_remote_trigger("example_task_complete", {"corpus_count": 250, "next_action": "fine_tune_9b"})
    print("AGENT_TRIGGERS_REMOTE ready for KAIROS integration")