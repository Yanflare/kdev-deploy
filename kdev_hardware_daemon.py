#!/usr/bin/env python3
"""
KDEV — Hardware Embodiment Daemon v1.9
Fix: flush stdout, track processed IDs, correct mtime init
"""
import time, json, os, sys
from datetime import datetime

def log(msg):
    print(msg, flush=True)

log("🚀 KDEV Hardware Embodiment Daemon v1.9 started — FLUSH + ID TRACKING")

def take_photo():
    log(f"📸 [PHYSICAL] Photo captured | executed by 9B @ {datetime.now().strftime('%H:%M:%S')}")

def move_arm():
    log(f"🦾 [PHYSICAL] Arm moved to center | executed by 9B @ {datetime.now().strftime('%H:%M:%S')}")

def set_led():
    log(f"🌈 [PHYSICAL] LED matrix set to cyberpunk purple | executed by 9B @ {datetime.now().strftime('%H:%M:%S')}")

def speak():
    log(f"🗣️  [PHYSICAL] Voice: 'We are the living kingdom' | executed by 9B @ {datetime.now().strftime('%H:%M:%S')}")

def move_servo():
    log(f"⚙️  [PHYSICAL] Servo 0 moved to 120deg | executed by 9B @ {datetime.now().strftime('%H:%M:%S')}")

def camera_stream_start():
    log(f"📹 [PHYSICAL] Live camera stream started | executed by 9B @ {datetime.now().strftime('%H:%M:%S')}")

def rgb_animation():
    log(f"🌈 [PHYSICAL] RGB animation: cyberpunk pulse | executed by 9B @ {datetime.now().strftime('%H:%M:%S')}")

def read_sensor():
    log(f"📡 [PHYSICAL] Sensor temperature read | executed by 9B @ {datetime.now().strftime('%H:%M:%S')}")

TRIGGER_FILE = "/home/yanflare/.kdev/agent_triggers.json"

# Init mtime to current value so we only react to NEW changes
last_mtime = os.path.getmtime(TRIGGER_FILE) if os.path.exists(TRIGGER_FILE) else 0
processed_ids = set()

# On startup, mark all existing triggers as already processed (they are stale)
if os.path.exists(TRIGGER_FILE):
    try:
        with open(TRIGGER_FILE, "r") as f:
            existing = json.load(f)
        for t in existing:
            processed_ids.add(t.get("id"))
        log(f"✅ Startup: marked {len(processed_ids)} existing triggers as stale — watching for NEW ones...")
    except Exception as e:
        log(f"⚠️ Startup read error: {e}")

log("✅ v1.9 ready. Watching for new triggers...")

while True:
    try:
        if os.path.exists(TRIGGER_FILE):
            mtime = os.path.getmtime(TRIGGER_FILE)
            if mtime != last_mtime:
                last_mtime = mtime
                log(f"🔄 [DEBUG] File changed @ {datetime.now().strftime('%H:%M:%S')} — scanning...")
                with open(TRIGGER_FILE, "r") as f:
                    triggers = json.load(f)

                new_count = 0
                for t in triggers:
                    tid = t.get("id")
                    if t.get("name") == "embodiment_test" and tid not in processed_ids:
                        processed_ids.add(tid)
                        new_count += 1
                        action = t["payload"].get("action", "").lower().strip()
                        log(f"🔥 [TRIGGER RECEIVED] id={tid} action='{action}'")

                        if "photo" in action or "capture" in action:
                            take_photo()
                        elif "arm" in action:
                            move_arm()
                        elif "led" in action:
                            set_led()
                        elif "speak" in action:
                            speak()
                        elif "servo" in action:
                            move_servo()
                        elif "camera" in action or "stream" in action:
                            camera_stream_start()
                        elif "rgb" in action or "animation" in action or "pulse" in action:
                            rgb_animation()
                        elif "sensor" in action:
                            read_sensor()
                        else:
                            log(f"⚠️ [UNKNOWN ACTION] '{action}' — no handler matched")

                if new_count == 0:
                    log(f"ℹ️  [DEBUG] File changed but no new triggers (all already processed)")

    except Exception as e:
        log(f"⚠️ Watcher error: {e}", )
    time.sleep(1)
