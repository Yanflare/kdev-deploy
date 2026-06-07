#!/usr/bin/env python3
"""
KDEV TERMINAL UI v1.1 — Cyberpunk KDE Operator Console
Primary reference: Your cyan hooded operator + red-alert concept
"""

import asyncio
import json
import subprocess
import time
from pathlib import Path
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, DataTable, RichLog, Input
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from rich.text import Text

KDEV_VERSION = "Phase 2A — Corpus 104+"
FINETUNE_PATH = Path("/home/yanflare/.kdev/finetune.jsonl")
LOG_SERVICES = ["kdev-kairos", "kdev-auto-dream", "kdev-orchestrator"]


class KDEVApp(App):
    CSS = """
    Screen {
        background: #0a0a0a;
        color: #cccccc;
    }
    Header {
        background: #001122;
        color: #00f5ff;
        text-style: bold;
    }
    Footer {
        background: #001122;
        color: #00f5ff;
    }
    .panel {
        border: solid #00f5ff;
        background: #111111;
        padding: 1;
    }
    .logo { color: #00f5ff; text-style: bold; }
    .status-good { color: #00ff9d; }
    .status-alert { color: #ff0033; }
    .neon-cyan { color: #00f5ff; text-style: bold; }
    .neon-red { color: #ff0033; text-style: bold; }
    RichLog { background: #0a0a0a; }
    DataTable { background: #111111; }
    """

    corpus_count = reactive(104)
    kairos_beat = reactive("●")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container():
            with Horizontal():
                # LEFT: Live Logs
                with Vertical(classes="panel"):
                    yield Static("LIVE LOGS [KAIROS + autoDream]", classes="logo")
                    self.logs = RichLog(highlight=True, wrap=True, auto_scroll=True, max_lines=200)
                    yield self.logs

                # CENTER: ReAct Traces
                with Vertical(classes="panel"):
                    yield Static("✿ ReAct TRACES + CORPUS", classes="logo")
                    self.traces = DataTable(expand=True)
                    self.traces.add_columns("TIME", "✿", "PREVIEW")
                    yield self.traces

                # RIGHT: System Status
                with Vertical(classes="panel"):
                    yield Static("SYSTEM STATUS", classes="logo")
                    self.status = Static("", expand=True)
                    yield self.status

        # Bottom command input
        yield Input(placeholder="Type command here... (enter to send to orchestrator)", id="cmd_input")
        yield Footer()

    async def on_mount(self) -> None:
        self.title = f"KDEV TERMINAL — {KDEV_VERSION}"
        self.sub_title = "Cyberpunk KDE Operator Console"

        self.update_corpus()
        self.update_status()
        self.load_recent_traces()

        asyncio.create_task(self.live_log_stream())
        asyncio.create_task(self.live_corpus_watcher())
        asyncio.create_task(self.kairos_heartbeat())

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
        self.traces.add_columns("TIME", "✿", "PREVIEW")
        try:
            with open(FINETUNE_PATH, "r") as f:
                lines = f.readlines()[-15:]
            for line in reversed(lines):
                data = json.loads(line)
                ts = time.strftime("%H:%M:%S", time.localtime(data.get("ts", 0)))
                content = data["messages"][1]["content"] if len(data["messages"]) > 1 else ""
                preview = (content[:70] + "…") if len(content) > 70 else content
                marker = "✿" if "✿" in content else " "
                self.traces.add_row(ts, marker, preview)
        except:
            self.traces.add_row("—", " ", "No traces yet")

    async def live_log_stream(self):
        while True:
            try:
                for svc in LOG_SERVICES:
                    output = subprocess.check_output(
                        ["journalctl", "-u", f"{svc}.service", "--no-pager", "-n", "5", "--since", "30 seconds ago"],
                        text=True
                    ).strip()
                    if output:
                        self.logs.write(f"[#00f5ff][{svc.upper()}][/] {output}\n")
            except:
                pass
            await asyncio.sleep(6)

    async def live_corpus_watcher(self):
        while True:
            self.update_corpus()
            self.update_status()
            self.load_recent_traces()
            await asyncio.sleep(10)

    async def kairos_heartbeat(self):
        idx = 0
        while True:
            self.kairos_beat = "●" if idx % 2 == 0 else "○"
            self.title = f"KDEV TERMINAL — {KDEV_VERSION}  KAIROS {self.kairos_beat}"
            idx += 1
            await asyncio.sleep(1.3)

    def on_input_submitted(self, event):
        cmd = event.value.strip()
        if cmd:
            self.logs.write(f"[#ff0033]→ Sent to orchestrator: {cmd}[/]")
            # TODO: future hook to real orchestrator endpoint
            event.input.clear()

    def on_key(self, event):
        if event.key == "r":
            self.update_corpus()
            self.update_status()
            self.load_recent_traces()
            self.logs.write("[#00ff9d]Manual refresh[/]")
        elif event.key == "c":
            self.logs.clear()
            self.logs.write("[#00f5ff]Logs cleared[/]")
        elif event.key == "q":
            self.exit()


if __name__ == "__main__":
    app = KDEVApp()
    app.run()