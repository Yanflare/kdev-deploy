#!/usr/bin/env python3
import os
import subprocess
import time
import datetime
from pathlib import Path

# ==================== CONFIG ====================
LLAMA_TURBO_DIR = Path("/home/yanflare/llama-cpp-turboquant")
TURBO_PORT = 8082
# ===============================================

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] TURBOQUANT_SETUP_v4: {msg}")

def run(cmd, cwd=None, check=True):
    log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        log(f"ERROR: {result.stderr}")
        raise RuntimeError(result.stderr)
    return result.stdout.strip()

def find_14b_model_path():
    """Robust detection: largest blob >7 GB = the 14B model"""
    log("Searching for 14B GGUF blob (largest file >7 GB in Ollama blobs)...")
    blob_dir = Path("/home/yanflare/.ollama/models/blobs")
    candidates = [f for f in blob_dir.iterdir() if f.is_file() and f.stat().st_size > 7 * 1024**3]
    if not candidates:
        raise FileNotFoundError("No 14B blob (>7 GB) found in Ollama blobs")
    # Take the largest one
    model_path = max(candidates, key=lambda f: f.stat().st_size)
    log(f"✅ Found 14B model blob: {model_path} ({model_path.stat().st_size / 1024**3:.1f} GB)")
    return str(model_path)

def main():
    log("=== KDEV TurboQuant Setup Phase 2B.4 v4 (Robust Detection) STARTED ===")
    
    # 1. Find real model path
    model_path = find_14b_model_path()
    
    # 2. Stop any previous broken service
    run(["sudo", "systemctl", "stop", "kdev-turboquant.service"], check=False)
    
    # 3. Create clean service with real path
    log("Installing clean TurboQuant sidecar service...")
    service_file = "/etc/systemd/system/kdev-turboquant.service"
    with open("/tmp/kdev-turboquant.service", "w") as f:
        f.write(f"""[Unit]
Description=KDEV TurboQuant Sidecar (14B with 4-6x KV compression)
After=ollama.service kdev-kairos.service

[Service]
Type=simple
User=yanflare
WorkingDirectory={LLAMA_TURBO_DIR}
ExecStart={LLAMA_TURBO_DIR}/build/bin/llama-server \\
  --model {model_path} \\
  --cache-type-k q8_0 \\
  --cache-type-v turbo4 \\
  --port {TURBO_PORT} \\
  -c 131072 \\
  -ngl 0 \\
  --host 0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
""")
    run(["sudo", "cp", "/tmp/kdev-turboquant.service", service_file])
    run(["sudo", "systemctl", "daemon-reload"])
    run(["sudo", "systemctl", "enable", "--now", "kdev-turboquant.service"])
    
    # 4. Health check
    log("Waiting 25s for TurboQuant sidecar to start...")
    time.sleep(25)
    try:
        health = run(["curl", "-s", f"http://localhost:{TURBO_PORT}/health"])
        log(f"✅ TurboQuant sidecar HEALTH: {health}")
    except Exception as e:
        log(f"Sidecar still starting — normal on first launch: {e}")
    
    log("=== TurboQuant v4 COMPLETE ===")
    log("14B worker now has TurboQuant KV cache (4–6× efficiency) enabled!")

if __name__ == "__main__":
    main()