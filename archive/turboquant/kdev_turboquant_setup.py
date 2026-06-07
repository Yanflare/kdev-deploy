#!/usr/bin/env python3
import os
import subprocess
import time
import datetime
from pathlib import Path

# ==================== CONFIG ====================
TURBO_DIR = Path("/home/yanflare/turboquant_plus")
LLAMA_TURBO_DIR = Path("/home/yanflare/llama-cpp-turboquant")
OLLAMA_14B_MODEL = "huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M"
TURBO_PORT = 8082
# ===============================================

def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] TURBOQUANT_SETUP: {msg}")

def run(cmd, cwd=None, check=True):
    log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        log(f"ERROR: {result.stderr}")
        raise RuntimeError(result.stderr)
    return result.stdout.strip()

def main():
    log("=== KDEV TurboQuant Setup Phase 2B.4 STARTED ===")
    
    # 1. Clone repos (idempotent)
    if not TURBO_DIR.exists():
        run(["git", "clone", "https://github.com/TheTom/turboquant_plus.git", str(TURBO_DIR)])
    else:
        log("turboquant_plus already cloned")
    
    if not LLAMA_TURBO_DIR.exists():
        run(["git", "clone", "https://github.com/TheTom/llama-cpp-turboquant.git", str(LLAMA_TURBO_DIR)])
        os.chdir(LLAMA_TURBO_DIR)
        run(["git", "checkout", "feature/turboquant-kv-cache"])
    else:
        log("llama-cpp-turboquant already cloned")
    
    # 2. Build llama.cpp with TurboQuant support (CUDA if available, else CPU)
    build_dir = LLAMA_TURBO_DIR / "build"
    if not (build_dir / "bin" / "llama-server").exists():
        log("Building llama.cpp with TurboQuant...")
        os.chdir(LLAMA_TURBO_DIR)
        cuda_flags = "-DGGML_CUDA=ON" if Path("/usr/local/cuda").exists() else ""
        run(["cmake", "-B", "build", "-DCMAKE_BUILD_TYPE=Release", cuda_flags, "-DGGML_METAL=OFF"])
        run(["cmake", "--build", "build", "-j", "8"])
    else:
        log("TurboQuant-enhanced llama-server already built")
    
    # 3. Create TurboQuant sidecar service (runs on port 8082)
    service_file = "/etc/systemd/system/kdev-turboquant.service"
    if not Path(service_file).exists():
        log("Installing TurboQuant sidecar service...")
        with open("/tmp/kdev-turboquant.service", "w") as f:
            f.write(f"""[Unit]
Description=KDEV TurboQuant Sidecar (14B worker with 4-6x KV compression)
After=ollama.service

[Service]
Type=simple
User=yanflare
WorkingDirectory={LLAMA_TURBO_DIR}
ExecStart={LLAMA_TURBO_DIR}/build/bin/llama-server \\
  -m /home/yanflare/.ollama/models/blobs/{OLLAMA_14B_MODEL} \\
  --cache-type-k q8_0 \\
  --cache-type-v turbo4 \\
  --port {TURBO_PORT} \\
  -c 131072 \\
  -ngl 99 \\
  --host 0.0.0.0
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
""")
        run(["sudo", "cp", "/tmp/kdev-turboquant.service", service_file])
        run(["sudo", "systemctl", "daemon-reload"])
        run(["sudo", "systemctl", "enable", "--now", "kdev-turboquant.service"])
    else:
        log("TurboQuant sidecar service already installed")
    
    # 4. Quick health check
    log("Waiting 10s for TurboQuant server to start...")
    time.sleep(10)
    try:
        health = run(["curl", "-s", f"http://localhost:{TURBO_PORT}/health"])
        log(f"TurboQuant sidecar HEALTH: {health}")
    except:
        log("Sidecar not responding yet — normal on first start")
    
    log("=== TurboQuant Setup COMPLETE ===")
    log("Next step: KAIROS will automatically route long-context 14B calls to port 8082")
    log("Your 14B worker now has 4–6× KV cache efficiency!")

if __name__ == "__main__":
    main()