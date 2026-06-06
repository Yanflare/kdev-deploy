#!/usr/bin/env python3
"""
KDEV TERMINAL UI v1.0 — Cyberpunk KDE-Inspired TUI
Primary reference: Your cyan hooded operator concept
Author: Grok (Co-Engineer Partner) — 2026-04-01
"""

import asyncio
import json
import subprocess
import time
from pathlib import Path
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, DataTable, RichLog
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.color import Color
from rich.text import Text
from rich.console import Console

KDEV_VERSION = "Phase 2A — Corpus 101+"
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
    }
    .status-good { color: #00ff9d; }
    .status-alert { color: #ff0033; }
    .logo { color: #00f5ff; text-style: bold; }
    """

    corpus_count = reactive(101)
    kairos_beat = reactive("●")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container():
            with Horizontal():
                # LEFT: Live Logs
                with Vertical(classes="panel"):
                    yield Static("LIVE LOGS [KAIROS + autoDream]", classes="logo")
                    self.logs = RichLog(highlight=True, wrap=True, auto_scroll=True)
                    yield self.logs

                # CENTER: ReAct Trace Viewer
                with Vertical(classes="panel"):
                    yield Static("✿ ReAct TRACES + CORPUS", classes="logo")
                    self.traces = DataTable()
                    self.traces.add_columns("TS", "✿", "Preview")
                    yield self.traces

                # RIGHT: System Status
                with Vertical(classes="panel"):
                    yield Static("SYSTEM STATUS", classes="logo")
                    self.status = Static("", expand=True)
                    yield self.status

        yield Footer()

    async def on_mount(self) -> None:
        self.title = f"KDEV TERMINAL — {KDEV_VERSION}"
        self.sub_title = "Cyberpunk KDE Operator Console"

        # Initial population
        self.update_corpus()
        self.update_status()
        self.load_recent_traces()

        # Live refresh tasks
        asyncio.create_task(self.live_log_watcher())
        asyncio.create_task(self.live_corpus_watcher())
        asyncio.create_task(self.kairos_heartbeat())

    def update_corpus(self) -> None:
        try:
            count = int(subprocess.check_output(["wc", "-l", str(FINETUNE_PATH)], text=True).split()[0])
            self.corpus_count = count
        except Exception:
            self.corpus_count = 0

    def update_status(self) -> None:
        lines = []
        for svc in LOG_SERVICES:
            try:
                status = subprocess.check_output(["systemctl", "is-active", f"{svc}.service"], text=True).strip()
                color = "status-good" if status == "active" else "status-alert"
                lines.append(f"[{color}]{svc:20} ● {status.upper()}[/]")
            except Exception:
                lines.append(f"[status-alert]{svc:20} ● ERROR[/]")
        
        turbo = "16.4G RUNNING" if subprocess.run(["curl", "-s", "http://localhost:8082/health"], capture_output=True).returncode == 0 else "OFFLINE"
        lines.append(f"[#00ff9d]TurboQuant 14B      ● {turbo}[/]")
        lines.append(f"[#00f5ff]Corpus Records      ● {self.corpus_count}/300[/]")

        self.status.update("\n".join(lines))

    def load_recent_traces(self) -> None:
        self.traces.clear()
        self.traces.add_columns("TS", "✿", "Preview")
        try:
            with open(FINETUNE_PATH, "r") as f:
                lines = f.readlines()[-12:]  # last 12 records
            for line in reversed(lines):
                try:
                    data = json.loads(line)
                    ts = time.strftime("%H:%M:%S", time.localtime(data.get("ts", 0)))
                    content = data["messages"][1]["content"] if len(data["messages"]) > 1 else ""
                    preview = content[:60].replace("\n", " ") + "..." if len(content) > 60 else content
                    marker = "✿" if "✿" in content else " "
                    self.traces.add_row(ts, marker, preview)
                except Exception:
                    continue
        except Exception:
            self.traces.add_row("ERROR", " ", "Could not read finetune.jsonl")

    async def live_log_watcher(self) -> None:
        while True:
            try:
                for svc in LOG_SERVICES:
                    output = subprocess.check_output(
                        ["journalctl", "-u", f"{svc}.service", "--no-pager", "-n", "3", "--since", "60 seconds ago"],
                        text=True
                    ).strip()
                    if output:
                        self.logs.write(output, highlight=True)
            except Exception:
                pass
            await asyncio.sleep(8)

    async def live_corpus_watcher(self) -> None:
        while True:
            self.update_corpus()
            self.update_status()
            self.load_recent_traces()
            await asyncio.sleep(12)

    async def kairos_heartbeat(self) -> None:
        colors = ["#00f5ff", "#ff0033"]
        idx = 0
        while True:
            self.kairos_beat = "●" if idx % 2 == 0 else "○"
            self.title = f"KDEV TERMINAL — {KDEV_VERSION}  KAIROS {self.kairos_beat}"
            idx += 1
            await asyncio.sleep(1.2)

    def on_key(self, event) -> None:
        if event.key == "r":
            self.update_corpus()
            self.update_status()
            self.load_recent_traces()
            self.logs.write("[#00ff9d]Manual refresh triggered[/]")
        elif event.key == "q":
            self.exit()


if __name__ == "__main__":
    app = KDEVApp()
    app.run()