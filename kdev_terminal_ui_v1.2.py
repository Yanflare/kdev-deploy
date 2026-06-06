#!/usr/bin/env python3
"""
KDEV TERMINAL UI v1.2 — Cyberpunk KDE Operator Console (fixed for Textual 8.2.1)
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
        height: 100%;
    }
    .logo { color: #00f5ff; text-style: bold; }
    .status-good { color: #00ff9d; }
    .status-alert { color: #ff0033; }
    .neon-cyan { color: #00f5ff; text-style: bold; }
    .neon-red { color: #ff0033; text-style: bold; }
    RichLog { background: #0a0a0a; }
    DataTable { background: #111111; width: 100%; height: 100%; }
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
                    self.traces = DataTable()          # ← expand removed (Textual 8.2.1)
                    self.traces.expand = True          # ← this is the correct way now
                    self.traces.add_columns("TIME", "✿", "PREVIEW")
                    yield self.traces

                # RIGHT: System Status
                with Vertical(classes="panel"):
                    yield Static("SYSTEM STATUS", classes="logo")
                    self.status = Static("", expand=True)
                    yield self.status

        # Bottom command input
        yield Input(placeholder="Type command here... (enter to send)", id="cmd_input")
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
        
        turbo_ok = subprocess.run(["curl",