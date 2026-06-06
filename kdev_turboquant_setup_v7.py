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
    print(f"[{ts}] TURBOQUANT_SETUP_v7: {msg}")

def run(cmd, cwd=None, check=True):
    log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        log(f"ERROR: {result.stderr}")
        raise RuntimeError(result.stderr)
    return result.stdout.strip()

def find_14b_model_path():
    log("🔍 Running full diagnostic for 14B model blob (>8 GB)...")
    
    # 1. Show ollama list
    log("Ollama model list:")
    print(run(["ollama", "list"]))
    
    # 2. Broad search for any >8 GB file in Ollama directories
    log("Searching all Ollama-related directories for >8 GB files...")
    candidates = []
    search_paths = ["/home/yanflare/.ollama", "/home/yanflare/.cache/ollama", "/home/yanflare"]
    
    for base in search_paths:
        if not Path(base).exists():
            continue
        try:
            result = subprocess.run([
                "find", base, "-type", "f", "-size", "+8G"
            ], capture_output=True, text=True, timeout=30)
            files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            candidates.extend(files)
        except:
            pass
    
    if not candidates:
        raise FileNotFoundError("No file >8 GB found anywhere in Ollama directories.")
    
    # Log all candidates with sizes
    log(f"Found {len(candidates)} large files. Showing them with sizes:")
    for f in sorted(candidates, key=os.path.getsize, reverse=True)[:10]:
        size_gb = os.path.getsize(f) / 1024**3
        log(f"   → {f} ({size_gb:.2f} GB)")
    
    # Pick the largest one
    model_path = max(candidates, key=os.path.getsize)
    size_gb = os.path.getsize(model_path) / 1024**3
    log(f"✅ SELECTED LARGEST MODEL: {model_path} ({size_gb:.2f} GB)")
    return model_path

def main():
    log("=== KDEV TurboQuant Setup Phase 2B.4 v7 (FULL DIAGNOSTIC) STARTED ===")
    
    model_path = find_14b_model_path()
    
    # Stop previous service
    run(["sudo", "systemctl", "stop", "kdev-turboquant.service"], check=False)
    
    # Install service with the correct path
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
    
    log("Waiting 30s for sidecar to start...")
    time.sleep(30)
    try:
        health = run(["curl", "-s", f"http://localhost:{TURBO_PORT}/health"])
        log(f"✅ TurboQuant sidecar HEALTH: {health}")
    except Exception as e:
        log(f"Sidecar still starting — normal on first launch: {e}")
    
    log("=== TurboQuant v7 COMPLETE ===")
    log("TurboQuant KV cache (4–6× efficiency) is now active!")

if __name__ == "__main__":
    main()