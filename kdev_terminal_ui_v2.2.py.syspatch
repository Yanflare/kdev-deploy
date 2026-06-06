#!/usr/bin/env python3
"""
KDEV TERMINAL UI v2.2 — Cyberpunk KDE Operator Console
Compatible with Textual 8.x
Changes vs v2.1:
  - command_log: RichLog → read-only TextArea (text is now selectable/copyable)
  - /paste slash command: reads /tmp/kdev_paste.txt into the input field
  - _log_write / _log_clear helpers centralise all log updates
  - redraw() during streaming rebuilt with load_text() for TextArea
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
from textual.widgets import DataTable, Input, Label, ListView, ListItem, RichLog, Static, TextArea

FINETUNE_PATH = Path("/home/yanflare/.kdev/finetune.jsonl")
LOG_SERVICES  = ["kdev-kairos", "kdev-auto-dream", "kdev-orchestrator"]
ORCH_URL      = "http://localhost:8080/chat"

# Strip Rich/Textual markup tags so plain text can be loaded into TextArea
_MARKUP_RE = re.compile(r'\[/?[^\]]*\]')

SLASH_COMMANDS = {
    "/status":  "Show full system status",
    "/logs":    "Show live log panel",
    "/corpus":  "Show corpus record count",
    "/restart": "Restart all KDEV services",
    "/clear":   "Clear the command chat log",
    "/dream":   "Trigger autoDream cycle manually",
    "/kairos":  "Ping Kairos and show heartbeat",
    "/help":    "List all available slash commands",
    "/paste":   "Paste from /tmp/kdev_paste.txt into input",
    "/mind":    "Route to 9B Orchestrator (reasoning/planning)",
    "/muscle":  "Route to 14B Worker (fast execution) [default]",
    "/synapse": "Route via full pipeline (decompose->execute->aggregate)",
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


class ChatInput(TextArea):
    """
    Multiline input that grows up to 6 rows.
    - Enter        → post Submitted message (send)
    - Shift+Enter  → insert a real newline
    - All other keys (including ctrl+v paste) pass through to TextArea natively.
    """

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def _on_key(self, event: Key) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            text = self.text.strip()
            if text:
                self.post_message(self.Submitted(text))
                self.clear()
        elif event.key == "shift+enter":
            event.stop()
            event.prevent_default()
            self.insert("\n")


# ── Main App ───────────────────────────────────────────────────────────────────

class KDEVApp(App):
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("escape", "collapse_panels", "Collapse panels", show=False),
    ]

    CSS = """
    Screen { background: #0a0a0a; color: #cccccc; }

    /* ── Single top bar that holds BOTH the title row and the tab row ── */
    #top_bar {
        dock: top;
        height: 2;
        background: #001122;
    }

    /* Title row inside top_bar */
    #header_bar {
        height: 1;
        background: #001122;
        padding: 0 1;
    }
    #header_beat  { width: 3;   content-align: left middle;   color: #00f5ff; }
    #header_title { width: 1fr; content-align: center middle; color: #00f5ff; text-style: bold; }
    #header_dot   { width: 12;  content-align: right middle; }

    /* Tab row inside top_bar */
    #panel_tabs { height: 1; }

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

    /* ── ChatInput docked to bottom — grows up to 6 rows ── */
    #cmd_input {
        dock: bottom;
        height: auto;
        min-height: 1;
        max-height: 6;
        background: #0a0a0a;
        border: solid #00f5ff;
        color: #cccccc;
    }

    /* ── Slash menu sits just above the input ── */
    #slash_menu {
        dock: bottom;
        display: none;
        height: auto;
        max-height: 12;
        background: #001122;
        border: solid #00f5ff;
    }
    #slash_menu > ListItem {
        padding: 0 2;
        background: #001122;
        color: #00f5ff;
    }
    #slash_menu > ListItem:hover       { background: #002244; color: #ff0033; }
    #slash_menu > ListItem.--highlight { background: #003366; color: #ffffff; }

    /* ── Main content fills the rest ── */
    #content_area { height: 1fr; }

    /* Expanded panel (hidden by default) */
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

    /* Chat zone */
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

    /* Shared */
    .status-good  { color: #00ff9d; }
    .status-alert { color: #ff0033; }
    RichLog   { background: #0a0a0a; height: 1fr; }
    DataTable { background: #111111; width: 100%; height: 1fr; }
    ScrollBar { background: transparent; color: #00f5ff; }

    /* Read-only command log — text is selectable and copyable */
    #command_log_area {
        background: #0a0a0a;
        height: 1fr;
        border: none;
        color: #cccccc;
        padding: 0 1;
    }
    """

    system_healthy: reactive[bool] = reactive(True)
    kairos_beat:    reactive[str]  = reactive("●")
    corpus_count:   reactive[int]  = reactive(0)
    routing_mode:   reactive[str]  = reactive("muscle")
    _expanded: str | None = None

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        # Single docked top bar: title row + tab row stacked vertically
        with Vertical(id="top_bar"):
            with Horizontal(id="header_bar"):
                yield Static("●", id="header_beat")
                yield Static("KDEV TERMINAL — Operator Console", id="header_title")
                yield StatusDot(id="header_dot")
            with Horizontal(id="panel_tabs"):
                yield PanelHeader("[LOGS] LIVE LOGS [KAIROS + autoDream]", panel_id="logs")
                yield PanelHeader("[~] ReAct TRACES + CORPUS",              panel_id="traces")
                yield PanelHeader("[*] SYSTEM STATUS",                      panel_id="status")

        # ChatInput docked to bottom (declared before content so it docks first)
        yield ChatInput("", id="cmd_input")

        # Slash menu docked above input
        yield ListView(id="slash_menu")

        # Remaining content area
        with Vertical(id="content_area"):
            with Vertical(id="expanded_panel"):
                yield Static("", id="expanded_title")
                self.logs = RichLog(highlight=True, wrap=True, auto_scroll=True,
                                    max_lines=300, id="logs_content")
                self.traces = DataTable(id="traces_content")
                self.traces.add_columns("TIME", "~", "PREVIEW")
                self.status_body = Static("", expand=True, id="status_content")
                yield self.logs
                yield self.traces
                yield self.status_body

            with Vertical(id="chat_zone"):
                yield Static(
                    "COMMAND CHAT LOG — select text to copy  |  /paste to load /tmp/kdev_paste.txt",
                    id="chat_label",
                )
                # Read-only TextArea: text is selectable and copyable via terminal
                self.command_log = TextArea("", id="command_log_area", read_only=True)
                yield self.command_log

    async def on_mount(self) -> None:
        self._log_history: list[str] = []
        self._set_content_visibility(None)
        self.update_corpus()
        self.update_status()
        self.load_recent_traces()
        asyncio.create_task(self.live_log_stream())
        asyncio.create_task(self.live_corpus_watcher())
        asyncio.create_task(self.kairos_heartbeat())
        asyncio.create_task(self.live_health_checker())

    # ── Command-log helpers ───────────────────────────────────────────────────

    def _rebuild_log(self) -> None:
        """Reload the read-only TextArea from _log_history (markup stripped)."""
        lines = [_MARKUP_RE.sub("", e) for e in self._log_history if e is not None]
        try:
            self.command_log.load_text("\n".join(lines))
            self.command_log.scroll_end(animate=False)
        except Exception:
            pass

    def _log_write(self, rich_text: str) -> None:
        """Append one line to the command log."""
        self._log_history.append(rich_text)
        if len(self._log_history) > 200:
            self._log_history = self._log_history[-200:]
        self._rebuild_log()

    def _log_clear(self) -> None:
        """Clear the command log."""
        self._log_history = []
        try:
            self.command_log.load_text("")
        except Exception:
            pass

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_content_visibility(self, which: str | None) -> None:
        self.query_one("#logs_content").display   = (which == "logs")
        self.query_one("#traces_content").display = (which == "traces")
        self.query_one("#status_content").display = (which == "status")

    PANEL_TITLES = {
        "logs":   "[LOGS] LIVE LOGS — Esc to collapse",
        "traces": "[~] ReAct TRACES + CORPUS — Esc to collapse",
        "status": "[*] SYSTEM STATUS — Esc to collapse",
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

    def on_chat_input_changed(self, event: TextArea.Changed) -> None:
        val = self.query_one("#cmd_input", ChatInput).text
        if val.startswith("/"):
            self._show_slash_menu(val.split("\n")[0])
        else:
            self._hide_slash_menu()

    def on_key(self, event: Key) -> None:
        menu = self.query_one("#slash_menu", ListView)
        if not menu.display:
            return
        ta = self.query_one("#cmd_input", ChatInput)

        if event.key == "tab":
            event.stop()
            if menu.highlighted_child is not None:
                m = re.search(r"(/\w+)", str(menu.highlighted_child.query_one(Label).renderable))
                if m:
                    ta.clear()
                    ta.insert(m.group(1))
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
        m = re.search(r"(/\w+)", str(event.item.query_one(Label).renderable))
        if m:
            ta = self.query_one("#cmd_input", ChatInput)
            ta.clear()
            ta.insert(m.group(1))
        self._hide_slash_menu()

    # ── Command submission ────────────────────────────────────────────────────

    def on_chat_input_submitted(self, event: ChatInput.Submitted) -> None:
        cmd = event.value.strip()
        if not cmd:
            return
        self._hide_slash_menu()

        if cmd == "/clear":
            self._log_clear()
            return

        if cmd == "/help":
            self._log_write("[bold #00f5ff]Available commands:[/]")
            for c, d in SLASH_COMMANDS.items():
                self._log_write(f"  [#00f5ff]{c:14}[/] [#888888]{d}[/]")
            return

        if cmd == "/corpus":
            self.update_corpus()
            self._log_write(
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

        if cmd == "/paste":
            paste_path = Path("/tmp/kdev_paste.txt")
            if not paste_path.exists():
                self._log_write(
                    "[#ff0033]>> /tmp/kdev_paste.txt not found — "
                    "write your text there first[/]"
                )
            else:
                pasted = paste_path.read_text().strip()
                if pasted:
                    ta = self.query_one("#cmd_input", ChatInput)
                    ta.clear()
                    ta.insert(pasted)
                    self._log_write("[#00f5ff]>> Pasted from /tmp/kdev_paste.txt[/]")
                else:
                    self._log_write("[#ff0033]>> /tmp/kdev_paste.txt is empty[/]")
            return

        if cmd in ("/mind", "/muscle", "/synapse"):
            mode = cmd.lstrip("/")
            self.routing_mode = mode
            self._log_write(f"[bold #00f5ff]>> Mode switched to /{mode}[/]")
            return

        entry = f"[#00f5ff]-> YOU: {cmd}[/]"
        self._log_write(entry)
        asyncio.create_task(self._dispatch(cmd))

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
            issues = []
            try:
                r = subprocess.run(
                    ["curl", "-s", "--max-time", "2", "http://localhost:8080/health"],
                    capture_output=True, timeout=3
                )
                if r.returncode != 0:
                    healthy = False
                    issues.append("http://localhost:8080/health")
                for svc in LOG_SERVICES:
                    try:
                        st = subprocess.check_output(
                            ["systemctl", "is-active", f"{svc}.service"], text=True
                        ).strip()
                        if st != "active":
                            healthy = False
                            issues.append(svc)
                    except Exception:
                        healthy = False
                        issues.append(svc)
            except Exception:
                healthy = False

            prev = self.system_healthy
            self.system_healthy = healthy

            if prev != healthy:
                if healthy:
                    self._log_write("[#00ff9d]>> SYSTEM BACK ONLINE[/]")
                else:
                    self._log_write(
                        f"[#ff0033]>> SYSTEM OFFLINE — failing: {', '.join(issues)}[/]"
                    )
            await asyncio.sleep(2)

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
            ["curl", "-s", "--max-time", "2", "http://localhost:8080/health"],
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
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                try:
                    # Skip polluted corpus entries (system prompt injected as user message)
                    msgs_check = data.get("messages", [])
                    if any(
                        m.get("role") == "user" and
                        "You are KDEV Self-Healing Memory" in m.get("content", "")
                        for m in msgs_check
                    ):
                        continue

                    # Timestamp: prefer ISO timestamp field, then ts epoch, then created_at
                    ts = "——:——:——"
                    if data.get("timestamp"):
                        try:
                            ts = str(data["timestamp"])[11:19]
                        except Exception:
                            pass
                    elif data.get("fired_at"):
                        try:
                            ts = str(data["fired_at"])[11:19]
                        except Exception:
                            pass
                    else:
                        raw_ts = data.get("ts", 0)
                        if raw_ts and raw_ts > 86400:
                            ts = time.strftime("%H:%M:%S", time.localtime(raw_ts))
                        elif data.get("created_at"):
                            ts = str(data["created_at"])[:8]

                    # Preview: assistant turn only (never show system/user prompts)
                    preview = ""
                    msgs = data.get("messages", [])
                    for m in msgs:
                        if m.get("role") == "assistant":
                            candidate = m.get("content", "").strip()
                            if candidate and not candidate.startswith("{"):
                                preview = candidate
                                break
                            elif candidate.startswith("{"):
                                try:
                                    cd = json.loads(candidate)
                                    for field in ("workspace_observations", "improvement_actions", "tool_gaps", "physical_capability_gaps"):
                                        val = cd.get(field)
                                        if val:
                                            preview = val[0] if isinstance(val, list) else str(val)
                                            break
                                except Exception:
                                    pass
                                if preview:
                                    break

                    # Fall back to top-level fields only
                    if not preview:
                        for key in ("text", "output", "response"):
                            if data.get(key):
                                preview = str(data[key]).strip()
                                break

                    # Last resort: top-level text fields
                    if not preview:
                        for key in ("text", "output", "response", "prompt"):
                            if data.get(key):
                                preview = str(data[key]).strip()
                                break

                    if not preview:
                        continue   # skip unreadable records silently

                    marker = "✤" if any(
                        k in preview.lower()
                        for k in ("skill", "memory", "fix", "diagnosis", "consolidated", "analysis")
                    ) else "~"
                    preview_str = (preview[:78] + "…") if len(preview) > 78 else preview
                    self.traces.add_row(ts, marker, preview_str)
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

    _cookie_path  = "/tmp/kdev_cookie.txt"
    _cookie_ready = False

    def _do_login(self) -> bool:
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", "http://localhost:8080/login",
             "-c", self._cookie_path,
             "-d", "password=kdev"],
            capture_output=True, text=True, timeout=10,
        )
        ok = result.returncode == 0 and "401" not in result.stdout
        if ok:
            KDEVApp._cookie_ready = True
        return ok

    async def _send_to_orchestrator(self, cmd: str) -> None:
        try:
            loop = asyncio.get_event_loop()

            # Login once per session (or re-login on 401)
            if not KDEVApp._cookie_ready:
                ok = await loop.run_in_executor(None, self._do_login)
                if not ok:
                    self._log_write("[#ff0033]<- KDEV: login failed[/]")
                    return

            payload = json.dumps({"message": self.KDEV_SYSTEM_PROMPT + " " + cmd, "session_id": "tui"})

            assembled = []
            got_401 = False

            def redraw():
                """Rebuild TextArea with history + the currently-streaming token."""
                lines = [_MARKUP_RE.sub("", e) for e in self._log_history if e is not None]
                current = "".join(assembled)
                lines.append(f"<- KDEV: {current}")
                try:
                    self.command_log.load_text("\n".join(lines))
                    self.command_log.scroll_end(animate=False)
                except Exception:
                    pass

            def stream_to_ui(cookie_path):
                nonlocal got_401
                proc = subprocess.Popen(
                    ["curl", "-s", "-N", "-X", "POST", ORCH_URL,
                     "-H", "Content-Type: application/json",
                     "-b", cookie_path,
                     "-d", payload],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                for raw in proc.stdout:
                    line = raw.rstrip("\n")
                    if not line.startswith("data: "):
                        if "401" in line or "Unauthorized" in line:
                            got_401 = True
                        continue
                    chunk = line[6:]
                    if chunk.strip() == "[DONE]":
                        break
                    try:
                        token = json.loads(chunk)["token"]
                    except Exception:
                        continue
                    assembled.append(token)
                    self.app.call_from_thread(redraw)
                proc.wait()

            await loop.run_in_executor(None, lambda: stream_to_ui(self._cookie_path))

            # Re-login once if 401
            if got_401 or not assembled:
                KDEVApp._cookie_ready = False
                ok = await loop.run_in_executor(None, self._do_login)
                if not ok:
                    self._log_write("[#ff0033]<- KDEV: re-login failed[/]")
                    return
                assembled.clear()
                got_401 = False
                await loop.run_in_executor(None, lambda: stream_to_ui(self._cookie_path))

            final = "".join(assembled).strip() or "No final response"
            # _log_write appends to _log_history AND rebuilds the TextArea
            self._log_write(f"[#ff0033]<- KDEV: {final}[/]")
            self.logs.write(f"[#ff0033]KDEV RESPONSE: {final[:80]}...[/]")

        except Exception as e:
            self._log_write(f"[#ff0033]<- ERROR: {e}[/]")


    KDEV_SYSTEM_PROMPT = 'You are Kdev, an AI assistant running locally on a machine called Kiki. Hardware: AMD Radeon RX 6800 XT (gfx1030), 16 GB VRAM, ROCm 6.2.2. GPU monitoring: rocm-smi ONLY. Never suggest nvidia-smi or any CUDA/NVIDIA tool. OS: headless x86 Linux. No display, no GUI, no GPIO, no camera. DRM path: card1. VRAM idle: ~9.1 GB (TurboQuant 14B on port 8082). Peak: ~15.9 GB. Limit: 16 GB. Python: /home/yanflare/.kdev-venv/bin/python3 only - never system python3. Services: kdev-web 8080, bridge 8081, TurboQuant 14B 8082, 9B Ollama 11435. Port 11434 Ollama is IDLE. Deploy: /home/yanflare/kdev-deploy/. Config: /home/yanflare/.kdev/. CONFIDENCE_FLOOR=0.85. KAIROS cycle=600s. For hardware stats: use rocm-smi only, never nvidia-smi.'

    async def _dispatch(self, cmd: str) -> None:
        mode = self.routing_mode
        if mode == "mind":
            await self._send_to_mind(cmd)
        elif mode == "synapse":
            await self._send_to_synapse(cmd)
        else:
            await self._send_to_muscle(cmd)

    async def _send_to_muscle(self, cmd: str) -> None:
        import urllib.request as _ur
        url = "http://127.0.0.1:8082/v1/chat/completions"
        payload = json.dumps({
            "model": "huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M",
            "messages": [{"role": "system", "content": self.KDEV_SYSTEM_PROMPT}, {"role": "user", "content": cmd}],
            "stream": True,
        }).encode()
        assembled = []
        loop = asyncio.get_event_loop()

        def redraw():
            lines = [_MARKUP_RE.sub("", e) for e in self._log_history if e is not None]
            lines.append(f"<- MUSCLE: {''.join(assembled)}")
            try:
                self.command_log.load_text("\n".join(lines))
                self.command_log.scroll_end(animate=False)
            except Exception:
                pass

        def stream():
            proc = __import__("subprocess").Popen(
                ["curl", "-s", "-N", "-X", "POST", url,
                 "-H", "Content-Type: application/json",
                 "-d", payload.decode()],
                stdout=__import__("subprocess").PIPE,
                stderr=__import__("subprocess").PIPE,
                text=True,
            )
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                if not line.startswith("data: "):
                    continue
                chunk = line[6:]
                if chunk.strip() == "[DONE]":
                    break
                try:
                    token = json.loads(chunk)["choices"][0]["delta"].get("content")
                except Exception:
                    continue
                if not token:
                    continue
                assembled.append(token)
                self.app.call_from_thread(redraw)
            proc.wait()

        try:
            await loop.run_in_executor(None, stream)
            final = "".join(assembled).strip() or "No response from muscle"
            self._log_write(f"[#ff0033]<- MUSCLE: {final}[/]")
        except Exception as e:
            self._log_write(f"[#ff0033]<- MUSCLE ERROR: {e}[/]")

    async def _send_to_mind(self, cmd: str) -> None:
        url = "http://127.0.0.1:11435/api/chat"
        payload = json.dumps({
            "model": "kdev-orchestrator-9b-finetuned-v1:latest",
            "system": self.KDEV_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": cmd}],
            "stream": True,
        }).encode()
        assembled = []
        loop = asyncio.get_event_loop()

        def redraw():
            lines = [_MARKUP_RE.sub("", e) for e in self._log_history if e is not None]
            lines.append(f"<- MIND: {''.join(assembled)}")
            try:
                self.command_log.load_text("\n".join(lines))
                self.command_log.scroll_end(animate=False)
            except Exception:
                pass

        def stream():
            proc = __import__("subprocess").Popen(
                ["curl", "-s", "-N", "-X", "POST", url,
                 "-H", "Content-Type: application/json",
                 "-d", payload.decode()],
                stdout=__import__("subprocess").PIPE,
                stderr=__import__("subprocess").PIPE,
                text=True,
            )
            for raw in proc.stdout:
                line = raw.rstrip("\n")
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if not token:
                        continue
                    assembled.append(token)
                    self.app.call_from_thread(redraw)
                    if data.get("done", False):
                        break
                except Exception:
                    continue
            proc.wait()

        try:
            await loop.run_in_executor(None, stream)
            final = "".join(assembled).strip() or "No response from mind"
            self._log_write(f"[#ff0033]<- MIND: {final}[/]")
        except Exception as e:
            self._log_write(f"[#ff0033]<- MIND ERROR: {e}[/]")

    async def _send_to_synapse(self, cmd: str) -> None:
        url = "http://127.0.0.1:8081/orch/chat"
        payload = json.dumps({"message": cmd, "session_id": "tui"})
        loop = asyncio.get_event_loop()

        def call():
            import urllib.request as _ur
            req = _ur.Request(url,
                data=payload.encode(),
                headers={"Content-Type": "application/json"},
            )
            with _ur.urlopen(req, timeout=320) as r:
                return json.loads(r.read().decode())

        try:
            self._log_write("[#888888]>> Synapse pipeline running...[/]")
            data = await loop.run_in_executor(None, call)
            rtype = data.get("type", "?")
            steps = data.get("steps", [])
            final = data.get("final", "").strip() or "No response from synapse"
            self._log_write(f"[#00f5ff]>> Synapse pipeline type: {rtype}[/]")
            for i, step in enumerate(steps, 1):
                self._log_write(f"[#888888]  {i}. {step}[/]")
            self._log_write(f"[#ff0033]<- SYNAPSE: {final}[/]")
        except Exception as e:
            self._log_write(f"[#ff0033]<- SYNAPSE ERROR: {e}[/]")


if __name__ == "__main__":
    KDEVApp().run()
