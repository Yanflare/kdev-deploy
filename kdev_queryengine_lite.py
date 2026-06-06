#!/usr/bin/env python3
import os
import json
import time
import datetime
import subprocess
import argparse
from pathlib import Path
from collections import deque

# ==================== CONFIG ====================
CACHE_SIZE = 20  # last N conversations kept in memory
MAX_TOKENS_PER_CALL = 4000
OLLAMA_9B = "huihui_ai/qwen3.5-abliterated:9b-Claude"
OLLAMA_14B = "huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M"
UDS_SOCKET = Path("/tmp/kdev_queryengine.sock")
# ===============================================

class QueryEngineLite:
    def __init__(self):
        self.cache = deque(maxlen=CACHE_SIZE)  # (session_id, summary, timestamp)
        self.log("QueryEngine Lite v1.0 — Claude v2.1.88 pattern activated")

    def log(self, msg):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] QUERYENGINE: {msg}")

    def estimate_tokens(self, text):
        """Very rough but fast token estimate"""
        return len(text) // 4 + 10

    def add_to_cache(self, session_id, user_message, assistant_summary):
        entry = {
            "session_id": session_id,
            "summary": assistant_summary[:200],
            "ts": int(time.time())
        }
        self.cache.append(entry)
        self.log(f"Cache updated — {len(self.cache)}/{CACHE_SIZE} entries")

    def get_cached_context(self, session_id):
        """Return recent relevant history for the same session"""
        relevant = [e for e in self.cache if e["session_id"] == session_id]
        if relevant:
            return "\n".join([f"Previous: {e['summary']}" for e in relevant[-3:]])
        return ""

    def parallel_delegate(self, task1, task2=None):
        """Optional: fire two 14B calls in parallel when beneficial"""
        commands = []
        if task1:
            commands.append(["curl", "-s", "-X", "POST", "http://localhost:11434/api/chat",
                             "-H", "Content-Type: application/json",
                             "-d", json.dumps({"model": OLLAMA_14B, "messages": [{"role": "user", "content": task1}], "stream": False})])
        if task2:
            commands.append(["curl", "-s", "-X", "POST", "http://localhost:11434/api/chat",
                             "-H", "Content-Type: application/json",
                             "-d", json.dumps({"model": OLLAMA_14B, "messages": [{"role": "user", "content": task2}], "stream": False})])
        
        results = []
        for cmd in commands:
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=45).stdout
                results.append(json.loads(out).get("message", {}).get("content", "")[:300])
            except:
                results.append("DELEGATION_FAILED")
        return results

    def process_query(self, user_message, session_id="default"):
        """Main entry point — called by orchestrator or KAIROS"""
        self.log(f"Processing query for session {session_id}")

        cached_context = self.get_cached_context(session_id)
        token_est = self.estimate_tokens(user_message + cached_context)

        if token_est > MAX_TOKENS_PER_CALL:
            self.log("Token budget exceeded → splitting into parallel delegation")
            task1 = f"Short summary of: {user_message[:300]}"
            task2 = f"Detailed answer for: {user_message[300:]} with context: {cached_context}"
            results = self.parallel_delegate(task1, task2)
            final_answer = f"Summary: {results[0]}\n\nDetail: {results[1] if len(results)>1 else ''}"
        else:
            # Normal flow — send to 9B with cache
            prompt = f"Context from cache:\n{cached_context}\n\nUser: {user_message}\nAnswer concisely and mark final answer with ✿ if this is a training-worthy response."
            payload = {"model": OLLAMA_9B, "messages": [{"role": "user", "content": prompt}], "stream": False, "temperature": 0.2}
            
            try:
                out = subprocess.run(["curl", "-s", "-X", "POST", "http://localhost:11434/api/chat",
                                      "-H", "Content-Type: application/json", "-d", json.dumps(payload)],
                                     capture_output=True, text=True, timeout=45).stdout
                final_answer = json.loads(out).get("message", {}).get("content", "")
            except Exception as e:
                final_answer = f"QUERYENGINE_ERROR: {e}"

        # Store in cache for next cycle
        short_summary = final_answer[:150]
        self.add_to_cache(session_id, user_message, short_summary)

        return final_answer

def main():
    parser = argparse.ArgumentParser(description="KDEV QueryEngine Lite — Claude v2.1.88 Super Brain")
    parser.add_argument("--oneshot", action="store_true")
    parser.add_argument("--test", type=str, help="Test query")
    args = parser.parse_args()

    engine = QueryEngineLite()

    if args.test:
        result = engine.process_query(args.test, session_id="test-session")
        print(f"\n=== QUERYENGINE RESULT ===\n{result}\n")
        return

    # Daemon mode — listens for internal calls via UDS (future expansion)
    if UDS_SOCKET.exists():
        UDS_SOCKET.unlink()
    # For now we just keep it alive so KAIROS can call it later
    engine.log("QueryEngine Lite ready — cache + parallel delegation active")
    while True:
        time.sleep(60)  # idle daemon, ready for internal calls

if __name__ == "__main__":
    main()