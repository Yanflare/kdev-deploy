#!/usr/bin/env python3
"""
KDEV TERMINAL UI v1.8 — Cyberpunk KDE Operator Console
"""

import asyncio
import json
import subprocess
import time
from pathlib import Path
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, DataTable, RichLog, Input, Button
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive

KDEV_VERSION = "Phase 2A — Corpus 106+"
FINETUNE_PATH = Path("/home/yanflare/.kdev/finetune.jsonl")
LOG_SERVICES = ["kdev-kairos", "kdev-auto-dream", "kdev-orchestrator"]
ORCH_URL = "http://localhost:8080/orch/chat"


class KDEVApp(App):
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        ("?", "noop", None),      # kills ? overlay
        ("escape", "minimize", "Restore layout"),
    ]

    CSS = """
    Screen { background: #0a0a0a; color: #cccccc; }
    Header { background: #001122; color: #00f5ff; text-style: bold; }
    Footer { background: #001122; color: #00f5ff; }
    .panel { border: solid #00f5ff; background: #111111; padding: 1; height: 100%; }
    .logo { color: #00f5ff; text-style: bold; }
    .status-good { color: #00ff9d; }
    .status-alert { color: #ff0033; }
    RichLog { background: #0a0a0a; }
    DataTable { background: #111111; width: 100%; height: 100%; }
    ScrollBar { background: transparent; color: #00f5ff; }
    Button { background: transparent; border: none; color: #00f5ff; text-style: bold; }
    Button:hover { color: #ff0033; }
    .status-dot { color: #00ff9d; text-style: bold; }
    .status-dot.alert { color: #ff0033; text-style: bold; }
    """

    corpus_count = reactive(106)
    kairos_beat = reactive("●")
    system_healthy = reactive(True)   # green/red status

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container():
            with Horizontal():
                # LIVE LOGS
                with Vertical(classes="panel", id="logs_panel"):
                    yield Button("LIVE LOGS [KAIROS + autoDream]", classes="logo", id="logs_header")
                    self.logs = RichLog(highlight=True, wrap=True, auto_scroll=True, max_lines=300)
                    yield self.logs

                # ReAct TRACES
                with Vertical(classes="panel", id="traces_panel"):
                    yield Button("✿ ReAct TRACES + CORPUS", classes="logo", id="traces_header")
                    self.traces = DataTable()
                    self.traces.expand = True
                    self.traces.add_columns("TIME", "✿", "PREVIEW")
                    yield self.traces

                # SYSTEM STATUS
                with Vertical(classes="panel", id="status_panel"):
                    yield Button("SYSTEM STATUS", classes="logo", id="status_header")
                    self.status = Static("", expand=True)
                    yield self.status

            # BOTTOM COMMAND CHAT
            with Vertical(classes="panel"):
                yield Static("COMMAND CHAT LOG — Messages sent to KDEV", classes="logo")
                self.command_log = RichLog(highlight=True, wrap=True, auto_scroll=True, max_lines=50)
                yield self.command_log

        yield Input(placeholder="Type message → Send to KDEV", id="cmd_input")
        yield Footer()

    async def on_mount(self) -> None:
        self.title = "KDEV TERMINAL"
        self.sub_title = "Operator Console"

        self.update_corpus()
        self.update_status()
        self.load_recent_traces()

        asyncio.create_task(self.live_log_stream())
        asyncio.create_task(self.live_corpus_watcher())
        asyncio.create_task(self.kairos_heartbeat())
        asyncio.create_task(self.live_health_checker())   # new status dot task

    def on_button_pressed(self, event):
        panel_map = {
            "logs_header": "logs_panel",
            "traces_header": "traces_panel",
            "status_header": "status_panel",
        }
        panel_id = panel_map.get(event.button.id)
        if panel_id:
            panel = self.query_one(f"#{panel_id}")
            panel.focus()
            self.action_maximize()

    def on_key(self, event):
        if event.key == "escape":
            self.action_minimize()
        elif event.key == "r":
            self.update_corpus()
            self.update_status()
            self.load_recent_traces()
            self.logs.write("[#00ff9d]Manual refresh[/]")
        elif event.key == "c":
            self.logs.clear()
            self.logs.write("[#00f5ff]Logs cleared[/]")
        elif event.key == "q":
            self.exit()

    async def live_health_checker(self):
        while True:
            healthy = True
            # quick checks
            try:
                if subprocess.run(["curl", "-s", "http://localhost:8080/health"], capture_output=True, timeout=2).returncode != 0:
                    healthy = False
                if subprocess.run(["curl", "-s", "http://localhost:8082/health"], capture_output=True, timeout=2).returncode != 0:
                    healthy = False
                for svc in LOG_SERVICES:
                    status = subprocess.check_output(["systemctl", "is-active", f"{svc}.service"], text=True).strip()
                    if status != "active":
                        healthy = False
            except:
                healthy = False
            self.system_healthy = healthy
            await asyncio.sleep(5)

    # rest of methods (update_corpus, update_status, load_recent_traces, live_log_stream, etc.)
    def update_corpus(self):
        try:
            count = int(subprocess.check_output(["wc", "-l", str(FINETUNE_PATH)], text=True).split()[0])
            self.corpus_count = count
        except:
            pass

    def update_status(self):
        lines = []
        for svc in LOG_SERVICES:
            try:
                status = subprocess.check_output(["systemctl", "is-active", f"{svc}.service"], text=True).strip()
                icon = "●" if status == "active" else "○"
                color = "status-good" if status == "active" else "status-alert"
                lines.append(f"[{color}]{icon} {svc:18} {status.upper()}[/]")
            except:
                lines.append(f"[status-alert]○ {svc:18} ERROR[/]")
        
        turbo_ok = subprocess.run(["curl", "-s", "http://localhost:8082/health"], capture_output=True).returncode == 0
        turbo_line = f"[#00ff9d]● TurboQuant 14B      16.4G RUNNING[/]" if turbo_ok else "[status-alert]○ TurboQuant OFFLINE[/]"
        lines.append(turbo_line)
        lines.append(f"[#00f5ff]● Corpus Records      {self.corpus_count}/300[/]")

        self.status.update("\n".join(lines))

    def load_recent_traces(self):
        self.traces.clear()
        try:
            with open(FINETUNE_PATH, "r") as f:
                lines = f.readlines()[-18:]
            for line in reversed(lines):
                try:
                    data = json.loads(line.strip())
                    ts = time.strftime("%H:%M:%S", time.localtime(data.get("ts", 0)))
                    content = data["messages"][1].get("content", "") if "messages" in data and len(data["messages"]) > 1 else ""
                    preview = (content[:78] + "…") if len(content) > 78 else content
                    marker = "✿" if "✿" in content else " "
                    self.traces.add_row(ts, marker, preview)
                except:
                    continue
        except:
            self.traces.add_row("—", " ", "No traces yet")

    async def live_log_stream(self):
        while True:
            try:
                for svc in LOG_SERVICES:
                    output = subprocess.check_output(
                        ["journalctl", "-u", f"{svc}.service", "--no-pager", "-n", "5", "--since", "50 seconds ago"],
                        text=True
                    ).strip()
                    if output:
                        self.logs.write(f"[#00f5ff][{svc.upper()}][/] {output}\n")
            except:
                pass
            await asyncio.sleep(4)

    async def live_corpus_watcher(self):
        while True:
            self.update_corpus()
            self.update_status()
            self.load_recent_traces()
            await asyncio.sleep(8)

    async def kairos_heartbeat(self):
        idx = 0
        while True:
            self.kairos_beat = "●" if idx % 2 == 0 else "○"
            idx += 1
            await asyncio.sleep(1.3)

    def on_input_submitted(self, event):
        cmd = event.value.strip()
        if not cmd:
            return

        self.command_log.write(f"[#00f5ff]→ YOU: {cmd}[/]")

        try:
            payload = json.dumps({"message": cmd})
            result = subprocess.run([
                "curl", "-s", "-X", "POST", ORCH_URL,
                "-H", "Content-Type: application/json",
                "-d", payload
            ], capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0 and result.stdout:
                response = json.loads(result.stdout)
                final = response.get("final", "No final response")
                self.command_log.write(f"[#ff0033]← KDEV: {final[:120]}[/]")
                self.logs.write(f"[#ff0033]KDEV RESPONSE: {final[:80]}…[/]")
            else:
                self.command_log.write(f"[#ff0033]← KDEV: (no response)[/]")
        except Exception as e:
            self.command_log.write(f"[#ff0033]← ERROR: {e}[/]")

        event.input.clear()


if __name__ == "__main__":
    app = KDEVApp()
    app.run()