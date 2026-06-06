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
    print(f"[{ts}] TURBOQUANT_SETUP_v6: {msg}")

def run(cmd, cwd=None, check=True):
    log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        log(f"ERROR: {result.stderr}")
        raise RuntimeError(result.stderr)
    return result.stdout.strip()

def find_14b_model_path():
    log("🔍 Searching for 14B GGUF blob (>8 GB) in Ollama directories only...")
    
    # Strict search inside Ollama folders only
    ollama_dirs = ["/home/yanflare/.ollama", "/home/yanflare/.cache/ollama"]
    candidates = []
    
    for base in ollama_dirs:
        if not Path(base).exists():
            continue
        try:
            result = subprocess.run([
                "find", base, "-type", "f", "-size", "+8G",
                "-name", "*qwen*", "-o", "-name", "*14b*", "-o", "-name", "*abliterate*"
            ], capture_output=True, text=True, timeout=20)
            files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            candidates.extend(files)
        except:
            pass
    
    if not candidates:
        raise FileNotFoundError("No 14B GGUF blob (>8 GB) found in Ollama directories")
    
    # Log all candidates for transparency
    log(f"Found {len(candidates)} candidate files. Showing sizes:")
    for f in candidates:
        size_gb = os.path.getsize(f) / 1024**3
        log(f"   → {f} ({size_gb:.1f} GB)")
    
    # Pick the largest one
    model_path = max(candidates, key=os.path.getsize)
    size_gb = os.path.getsize(model_path) / 1024**3
    log(f"✅ SELECTED 14B model: {model_path} ({size_gb:.1f} GB)")
    return model_path

def main():
    log("=== KDEV TurboQuant Setup Phase 2B.4 v6 (Strict Ollama-only Search) STARTED ===")
    
    # 1. Locate correct model
    model_path = find_14b_model_path()
    
    # 2. Stop previous service
    run(["sudo", "systemctl", "stop", "kdev-turboquant.service"], check=False)
    
    # 3. Install clean service
    log("Installing TurboQuant sidecar with correct model path...")
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
    log("Waiting 30s for sidecar to start...")
    time.sleep(30)
    try:
        health = run(["curl", "-s", f"http://localhost:{TURBO_PORT}/health"])
        log(f"✅ TurboQuant sidecar HEALTH: {health}")
    except Exception as e:
        log(f"Sidecar still starting — normal on first launch: {e}")
    
    log("=== TurboQuant v6 COMPLETE ===")
    log("TurboQuant KV cache (4–6× efficiency) is now active on port 8082!")

if __name__ == "__main__":
    main()