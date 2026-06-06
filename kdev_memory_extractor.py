#!/usr/bin/env python3
"""
KDEV — Memory Extractor v1.0 (EXTRACT_MEMORIES + TEAMMEM port)
Extracted & upgraded from paoloanzn/free-code + instructkr/claw-code
Author: Grok (Co-Engineer Partner) — 2026-04-01
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

class KDEVMemoryExtractor:
    def __init__(
        self,
        finetune_path: str = "/home/yanflare/.kdev/finetune.jsonl",
        team_mem_path: str = "/home/yanflare/.kdev/team_mem.json",
        debug: bool = True
    ):
        self.finetune_path = Path(finetune_path)
        self.team_mem_path = Path(team_mem_path)
        self.debug = debug

        # Ensure directories exist
        self.finetune_path.parent.mkdir(parents=True, exist_ok=True)
        self.team_mem_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize team memory file if missing
        if not self.team_mem_path.exists():
            self.team_mem_path.write_text("[]\n")

        if self.debug:
            print(f"[KDEV-MEM] Extractor initialized | Corpus: {self.get_corpus_count()} | TeamMem: {self.get_team_mem_count()}")

    def get_corpus_count(self) -> int:
        """Returns current number of records in finetune.jsonl"""
        try:
            with open(self.finetune_path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except FileNotFoundError:
            return 0

    def get_team_mem_count(self) -> int:
        """Returns number of shared team memories"""
        try:
            data = json.loads(self.team_mem_path.read_text() or "[]")
            return len(data)
        except:
            return 0

    def extract_memories(self, prompt: str, response: str, context: Dict[str, Any] = None) -> List[Dict]:
        """
        Claude-superior post-query memory extraction.
        Returns list of structured memories ready for finetune.jsonl + team sharing.
        """
        if context is None:
            context = {}

        memories = []

        # Core extraction (you can later hook this to 9B/TurboQuant for even smarter parsing)
        base_memory = {
            "timestamp": datetime.now().isoformat(),
            "source": "auto_extract_memories",
            "prompt_hash": hash(prompt) % 1000000,  # lightweight dedup
            "messages": [
                {"role": "user", "content": prompt[:8000]},      # truncate for safety
                {"role": "assistant", "content": response[:8000]}
            ],
            "extracted_insights": self._parse_insights(response),
            "code_snippets": self._extract_code_snippets(response),
            "task_state": context.get("task_state", "unknown"),
            "confidence": 0.92,   # default high because we control the loop
        }

        memories.append(base_memory)

        # TEAMMEM sync — share to team file if marked important
        if len(response) > 300 or "plan" in response.lower() or "decision" in response.lower():
            team_entry = {
                **base_memory,
                "shared_by": "KAIROS",
                "shared_at": datetime.now().isoformat()
            }
            self._append_to_team_mem(team_entry)
            if self.debug:
                print(f"[KDEV-MEM] TEAMMEM synced → {self.team_mem_path}")

        return memories

    def _parse_insights(self, text: str) -> List[str]:
        """Simple but effective insight parser (can be upgraded with 9B call later)"""
        insights = []
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith(("-", "•", "→")) and len(line) > 15:
                insights.append(line[1:].strip())
            elif any(kw in line.lower() for kw in ["plan", "decision", "remember", "key", "important"]):
                insights.append(line[:120])
        return insights[:8]  # cap to keep jsonl clean

    def _extract_code_snippets(self, text: str) -> List[str]:
        """Pulls fenced code blocks"""
        import re
        snippets = re.findall(r'```(?:python|bash|sh)?\s*(.*?)```', text, re.DOTALL)
        return [s.strip() for s in snippets if s.strip()]

    def _append_to_team_mem(self, entry: Dict):
        """Atomic append to shared team memory file"""
        try:
            data = json.loads(self.team_mem_path.read_text() or "[]")
            data.append(entry)
            # Keep only last 500 entries to prevent bloat
            data = data[-500:]
            self.team_mem_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"[KDEV-MEM] TEAMMEM write failed: {e}")

    def append_to_corpus(self, memories: List[Dict]):
        """Append extracted memories to finetune.jsonl (training-ready format)"""
        with open(self.finetune_path, "a", encoding="utf-8") as f:
            for mem in memories:
                f.write(json.dumps(mem, ensure_ascii=False) + "\n")

        if self.debug:
            print(f"[KDEV-MEM] ✅ Appended {len(memories)} record(s) → Corpus now at {self.get_corpus_count()}/300")

    def process_query(self, prompt: str, response: str, context: Dict = None):
        """Main entrypoint — call this after every orchestrator/9B/TurboQuant response"""
        memories = self.extract_memories(prompt, response, context)
        self.append_to_corpus(memories)
        return len(memories)

# ─────────────────────────────────────────────────────────────
# QUICK USAGE (add this to autoDream or KAIROS loop)
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    extractor = KDEVMemoryExtractor()
    # Example test
    test_prompt = "Plan the next phase of KDEV autonomy"
    test_response = "We should implement agent triggers and plugin system next..."
    count = extractor.process_query(test_prompt, test_response)
    print(f"Extraction complete — {count} memories added")