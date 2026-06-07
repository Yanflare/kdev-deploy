#!/usr/bin/env python3
"""
KDEV TERMINAL UI v2.0 — Cyberpunk KDE Operator Console
Compatible with Textual 8.x
"""

import asyncio
import json
import re
import subprocess
import time
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Click, Key
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Input, Label, ListView, ListItem, RichLog, Static

FINETUNE_PATH = Path("/home/yanflare/.kdev/finetune.jsonl")
LOG_SERVICES  = ["kdev-kairos", "kdev-auto-dream", "kdev-orchestrator"]
ORCH_URL      = "http://localhost:8080/orch/chat"

SLASH_COMMANDS = {
    "/status":  "Show full system status",
    "/logs":    "Show live log panel",
    "/corpus":  "Show corpus record count",
    "/restart": "Restart all KDEV services",
    "/clear":   "Clear the command chat log",
    "/dream":   "Trigger autoDream cycle manually",
    "/kairos":  "Ping Kairos and show heartbeat",
    "/help":    "List all available slash commands",
}


# ── Custom widgets ─────────────────────────────────────────────────────────────

class PanelHeader(Static):
    class HeaderClicked(Message):
        def __init__(self, panel_id: str) -> None:
            super().__init__()
            self.panel_id = panel_id

    def __init__(self, label: str, panel_id: str, **kwargs) -> None:
        super().__init__(label, **kwargs)
        self._panel_id = panel_id

    def on_click(self, event: Click) -> None:
        event.stop()
        self.post_message(self.HeaderClicked(self._panel_id))


class StatusDot(Static):
    healthy: reactive[bool] = reactive(True)

    def render(self) -> str:
        return "[bold #00ff9d]● ONLINE[/]" if self.healthy else "[bold #ff0033]● OFFLINE[/]"


# ── Main App ───────────────────────────────────────────────────────────────────

class KDEVApp(App):
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("escape", "collapse_panels", "Collapse panels", show=False),
    ]

    CSS = """
    Screen {
        background: #0a0a0a;
        color: #cccccc;
        layers: base overlay;
    }

    /* ── Title bar — must come first in dock order ── */
    #header_bar {
        layer: base;
        dock: top;
        height: 1;
        background: #001122;
        color: #00f5ff;
        padding: 0 1;
    }
    #header_beat  { width: 3;   content-align: left middle;   color: #00f5ff; }
    #header_title { width: 1fr; content-align: center middle; color: #00f5ff; text-style: bold; }
    #header_dot   { width: 12;  content-align: right middle; }

    /* ── Panel tab row — second dock ── */
    #panel_tabs {
        layer: base;
        dock: top;
        height: 1;
    }
    PanelHeader {
        width: 1fr;
        height: 1;
        color: #00f5ff;
        text-style: bold;
        background: #001122;
        border-right: solid #004466;
        content-align: center middle;
        padding: 0 1;
    }
    PanelHeader:hover { color: #ff0033; background: #002244; }

    /* ── Input — docked to bottom ── */
    #cmd_input {
        layer: base;
        dock: bottom;
        background: #0a0a0a;
        border: solid #00f5ff;
        color: #cccccc;
    }

    /* ── Slash menu — overlay above input ── */
    #slash_menu {
        layer: overlay;
        display: none;
        dock: bottom;
        height: auto;
        max-height: 12;
        background: #001122;
        border: solid #00f5ff;
        offset: 0 -3;
    }
    #slash_menu > ListItem {
        padding: 0 2;
        background: #001122;
        color: #00f5ff;
    }
    #slash_menu > ListItem:hover        { background: #002244; color: #ff0033; }
    #slash_menu > ListItem.--highlight  { background: #003366; color: #ffffff; }

    /* ── Footer hidden ── */
    Footer { height: 0; display: none; }

    /* ── Main content area (between the two docked bars and input) ── */
    #content_area { height: 1fr; }

    /* ── Expanded panel ── */
    #expanded_panel {
        display: none;
        border: solid #00f5ff;
        background: #111111;
        padding: 0 1 1 1;
        height: 1fr;
    }
    #expanded_title {
        height: 1;
        color: #ff0033;
        text-style: bold;
        background: #001122;
        width: 100%;
        padding: 0 1;
        content-align: left middle;
    }

    /* ── Chat zone ── */
    #chat_zone {
        height: 1fr;
        border: solid #00f5ff;
        background: #111111;
        padding: 0 1 1 1;
    }
    #chat_label {
        height: 1;
        color: #00f5ff;
        text-style: bold;
        background: #001122;
        width: 100%;
        padding: 0 1;
    }

    /* ── Shared ── */
    .status-good  { color: #00ff9d; }
    .status-alert { color: #ff0033; }
    RichLog   { background: #0a0a0a; height: 1fr; }
    DataTable { background: #111111; width: 100%; height: 1fr; }
    ScrollBar { background: transparent; color: #00f5ff; }
    """

    system_healthy: reactive[bool] = reactive(True)
    kairos_beat:    reactive[str]  = reactive("●")
    corpus_count:   reactive[int]  = reactive(0)
    _expanded: str | None = None

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        # 1. Title bar (docked top first)
        with Horizontal(id="header_bar"):
            yield Static("●", id="header_beat")
            yield Static("KDEV TERMINAL — Operator Console", id="header_title")
            yield StatusDot(id="header_dot")

        # 2. Panel tabs (docked top second — appears below title bar)
        with Horizontal(id="panel_tabs"):
            yield PanelHeader("▶ LIVE LOGS [KAIROS + autoDream]", panel_id="logs")
            yield PanelHeader("✿ ReAct TRACES + CORPUS",          panel_id="traces")
            yield PanelHeader("* SYSTEM STATUS",                   panel_id="status")

        # 3. Input (docked bottom)
        yield Input(placeholder="Type message or /command → KDEV", id="cmd_input")

        # 4. Slash menu (overlay, docked bottom, sits above input)
        yield ListView(id="slash_menu")

        # 5. Remaining content area
        with Vertical(id="content_area"):
            # Expanded panel slot (hidden by default)
            with Vertical(id="expanded_panel"):
                yield Static("", id="expanded_title")
                self.logs = RichLog(highlight=True, wrap=True, auto_scroll=True,
                                    max_lines=300, id="logs_content")
                self.traces = DataTable(id="traces_content")
                self.traces.add_columns("TIME", "✿", "PREVIEW")
                self.status_body = Static("", expand=True, id="status_content")
                yield self.logs
                yield self.traces
                yield self.status_body

            # Chat log
            with Vertical(id="chat_zone"):
                yield Static("COMMAND CHAT LOG — Messages sent to KDEV", id="chat_label")
                self.command_log = RichLog(highlight=True, wrap=True,
                                           auto_scroll=True, max_lines=200, id="cmd_log")
                yield self.command_log

        yield Footer()

    async def on_mount(self) -> None:
        self._set_content_visibility(None)
        self.update_corpus()
        self.update_status()
        self.load_recent_traces()
        asyncio.create_task(self.live_log_stream())
        asyncio.create_task(self.live_corpus_watcher())
        asyncio.create_task(self.kairos_heartbeat())
        asyncio.create_task(self.live_health_checker())

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_content_visibility(self, which: str | None) -> None:
        self.query_one("#logs_content").display    = (which == "logs")
        self.query_one("#traces_content").display  = (which == "traces")
        self.query_one("#status_content").display  = (which == "status")

    PANEL_TITLES = {
        "logs":   "▶ LIVE LOGS — Esc to collapse",
        "traces": "✿ ReAct TRACES + CORPUS — Esc to collapse",
        "status": "* SYSTEM STATUS — Esc to collapse",
    }

    # ── Panel expand / collapse ───────────────────────────────────────────────

    def on_panel_header_header_clicked(self, event: PanelHeader.HeaderClicked) -> None:
        pid = event.panel_id
        if self._expanded == pid:
            self.action_collapse_panels()
            return
        self._expanded = pid
        self._set_content_visibility(pid)
        self.query_one("#expanded_title", Static).update(self.PANEL_TITLES[pid])
        self.query_one("#expanded_panel").display = True
        self.query_one("#chat_zone").display = False

    def action_collapse_panels(self) -> None:
        self._expanded = None
        self._set_content_visibility(None)
        self.query_one("#expanded_panel").display = False
        self.query_one("#chat_zone").display = True
        self._hide_slash_menu()

    # ── Reactive watchers ─────────────────────────────────────────────────────

    def watch_system_healthy(self, healthy: bool) -> None:
        try:
            self.query_one("#header_dot", StatusDot).healthy = healthy
        except Exception:
            pass

    # ── Slash command menu ────────────────────────────────────────────────────

    def _show_slash_menu(self, prefix: str) -> None:
        menu = self.query_one("#slash_menu", ListView)
        menu.clear()
        matches = {k: v for k, v in SLASH_COMMANDS.items() if k.startswith(prefix)}
        if not matches:
            self._hide_slash_menu()
            return
        for cmd, desc in matches.items():
            menu.append(ListItem(Label(f"[bold #00f5ff]{cmd}[/]  [#555555]{desc}[/]")))
        menu.display = True
        menu.index = 0

    def _hide_slash_menu(self) -> None:
        self.query_one("#slash_menu", ListView).display = False

    def on_input_changed(self, event: Input.Changed) -> None:
        val = event.value
        if val.startswith("/"):
            self._show_slash_menu(val)
        else:
            self._hide_slash_menu()

    def on_key(self, event: Key) -> None:
        menu = self.query_one("#slash_menu", ListView)
        if not menu.display:
            return
        inp = self.query_one("#cmd_input", Input)

        if event.key == "tab":
            event.stop()
            if menu.highlighted_child is not None:
                raw = str(menu.highlighted_child.query_one(Label).renderable)
                m = re.search(r"(/\w+)", raw)
                if m:
                    inp.value = m.group(1)
                    inp.cursor_position = len(inp.value)
            self._hide_slash_menu()

        elif event.key == "down":
            event.stop()
            menu.action_cursor_down()

        elif event.key == "up":
            event.stop()
            menu.action_cursor_up()

        elif event.key == "escape":
            event.stop()
            self._hide_slash_menu()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        raw = str(event.item.query_one(Label).renderable)
        m = re.search(r"(/\w+)", raw)
        if m:
            inp = self.query_one("#cmd_input", Input)
            inp.value = m.group(1)
            inp.cursor_position = len(inp.value)
        self._hide_slash_menu()

    # ── Command submission ────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        cmd = event.value.strip()
        if not cmd:
            return
        self._hide_slash_menu()
        event.input.clear()

        if cmd == "/clear":
            self.command_log.clear()
            return
        if cmd == "/help":
            self.command_log.write("[bold #00f5ff]Available commands:[/]")
            for c, d in SLASH_COMMANDS.items():
                self.command_log.write(f"  [#00f5ff]{c:14}[/] [#888888]{d}[/]")
            return
        if cmd == "/corpus":
            self.update_corpus()
            self.command_log.write(
                f"[#00f5ff]Corpus records: [bold]{self.corpus_count}[/]/300[/]"
            )
            return
        if cmd == "/status":
            self.update_status()
            self._open_panel("status")
            return
        if cmd == "/logs":
            self._open_panel("logs")
            return

        self.command_log.write(f"[#00f5ff]→ YOU: {cmd}[/]")
        asyncio.create_task(self._send_to_orchestrator(cmd))

    def _open_panel(self, pid: str) -> None:
        self._expanded = pid
        self._set_content_visibility(pid)
        self.query_one("#expanded_title", Static).update(self.PANEL_TITLES[pid])
        self.query_one("#expanded_panel").display = True
        self.query_one("#chat_zone").display = False

    # ── Background tasks ──────────────────────────────────────────────────────

    async def live_health_checker(self) -> None:
        while True:
            healthy = True
            try:
                for url in ("http://localhost:8080/health", "http://localhost:8082/health"):
                    r = subprocess.run(["curl", "-s", "--max-time", "2", url],
                                       capture_output=True, timeout=3)
                    if r.returncode != 0:
                        healthy = False
                for svc in LOG_SERVICES:
                    st = subprocess.check_output(
                        ["systemctl", "is-active", f"{svc}.service"], text=True
                    ).strip()
                    if st != "active":
                        healthy = False
            except Exception:
                healthy = False
            self.system_healthy = healthy
            await asyncio.sleep(4)

    def update_corpus(self) -> None:
        try:
            self.corpus_count = int(
                subprocess.check_output(["wc", "-l", str(FINETUNE_PATH)], text=True).split()[0]
            )
        except Exception:
            pass

    def update_status(self) -> None:
        lines = []
        for svc in LOG_SERVICES:
            try:
                st    = subprocess.check_output(
                    ["systemctl", "is-active", f"{svc}.service"], text=True
                ).strip()
                icon  = "●" if st == "active" else "○"
                color = "status-good" if st == "active" else "status-alert"
                lines.append(f"[{color}]{icon} {svc:22} {st.upper()}[/]")
            except Exception:
                lines.append(f"[status-alert]○ {svc:22} ERROR[/]")
        turbo_ok = subprocess.run(
            ["curl", "-s", "--max-time", "2", "http://localhost:8082/health"],
            capture_output=True,
        ).returncode == 0
        lines.append(
            "[#00ff9d]● TurboQuant 14B        16.4G RUNNING[/]"
            if turbo_ok else
            "[status-alert]○ TurboQuant            OFFLINE[/]"
        )
        lines.append(f"[#00f5ff]● Corpus Records        {self.corpus_count}/300[/]")
        lines.append(f"\n[#00f5ff]KAIROS BEAT  {self.kairos_beat}[/]")
        try:
            self.status_body.update("\n".join(lines))
        except Exception:
            pass

    def load_recent_traces(self) -> None:
        self.traces.clear()
        try:
            with open(FINETUNE_PATH) as f:
                raw = f.readlines()[-18:]
            for line in reversed(raw):
                try:
                    data    = json.loads(line.strip())
                    ts      = time.strftime("%H:%M:%S", time.localtime(data.get("ts", 0)))
                    content = (
                        data["messages"][1].get("content", "")
                        if "messages" in data and len(data["messages"]) > 1
                        else ""
                    )
                    preview = (content[:78] + "…") if len(content) > 78 else content
                    marker  = "✿" if "✿" in content else " "
                    self.traces.add_row(ts, marker, preview)
                except Exception:
                    continue
        except Exception:
            self.traces.add_row("—", " ", "No traces yet")

    async def live_log_stream(self) -> None:
        while True:
            try:
                for svc in LOG_SERVICES:
                    output = subprocess.check_output(
                        ["journalctl", "-u", f"{svc}.service",
                         "--no-pager", "-n", "5", "--since", "50 seconds ago"],
                        text=True,
                    ).strip()
                    if output:
                        self.logs.write(f"[#00f5ff][{svc.upper()}][/] {output}\n")
            except Exception:
                pass
            await asyncio.sleep(4)

    async def live_corpus_watcher(self) -> None:
        while True:
            self.update_corpus()
            self.update_status()
            self.load_recent_traces()
            await asyncio.sleep(8)

    async def kairos_heartbeat(self) -> None:
        idx = 0
        while True:
            self.kairos_beat = "●" if idx % 2 == 0 else "○"
            try:
                self.query_one("#header_beat", Static).update(
                    "[#00f5ff]●[/]" if idx % 2 == 0 else "[#004466]○[/]"
                )
            except Exception:
                pass
            idx += 1
            await asyncio.sleep(1.3)

    async def _send_to_orchestrator(self, cmd: str) -> None:
        try:
            payload = json.dumps({"message": cmd})
            loop    = asyncio.get_event_loop()
            result  = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["curl", "-s", "-X", "POST", ORCH_URL,
                     "-H", "Content-Type: application/json",
                     "-d", payload],
                    capture_output=True, text=True, timeout=15,
                ),
            )
            if result.returncode == 0 and result.stdout:
                response = json.loads(result.stdout)
                final    = response.get("final", "No final response")
                self.command_log.write(f"[#ff0033]← KDEV: {final[:200]}[/]")
                self.logs.write(f"[#ff0033]KDEV RESPONSE: {final[:80]}…[/]")
            else:
                self.command_log.write("[#ff0033]← KDEV: (no response)[/]")
        except Exception as e:
            self.command_log.write(f"[#ff0033]← ERROR: {e}[/]")


if __name__ == "__main__":
    KDEVApp().run()
