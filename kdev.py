#!/usr/bin/env python3
"""
kdev.py — Private coding agent. Zero telemetry. Your backend, your data.

Backends (set in .env):
  BEDROCK:  AWS_BEARER_TOKEN_BEDROCK + AWS_REGION  (your $200 credits)
  LOCAL:    OLLAMA_BASE_URL + OLLAMA_MODEL          (when your PC arrives)
  DIRECT:   ANTHROPIC_API_KEY                       (fallback)
  GITHUB:   GITHUB_TOKEN                             (optional — enables GitHub MCP)

Usage:
  python kdev.py              — interactive mode
  python kdev.py "do X"       — single-shot mode
"""

import asyncio
import os
import sys
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import httpx
import struct
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# ── Rich output ────────────────────────────────────────────────────────────────
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
console = Console()

# ── prompt_toolkit input ───────────────────────────────────────────────────────
from prompt_toolkit import PromptSession as PTSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

# ── pydantic-ai ────────────────────────────────────────────────────────────────
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.models import Model, ModelRequestParameters, ModelSettings
from pydantic_ai.messages import (
    ModelMessage, ModelRequest, ModelResponse,
    SystemPromptPart, UserPromptPart, ToolReturnPart,
    TextPart, ToolCallPart,
)
from pydantic_ai.usage import Usage
from pydantic_ai.messages import ModelMessagesTypeAdapter

# ── Skills / self-learning ─────────────────────────────────────────────────────
from skills import (
    analyze_trace, maybe_write_skill, load_relevant_skills,
    list_skills, compress_session, self_debug_error,
)

# ── Config ─────────────────────────────────────────────────────────────────────
HOME         = Path.home()
KDEV_DIR     = HOME / ".kdev"
SESSIONS_DIR = KDEV_DIR / "sessions"
HISTORY_FILE = KDEV_DIR / "prompt_history"
MEMORY_FILE  = Path.cwd() / ".agent.md"
USER_MEMORY  = KDEV_DIR / "agent.md"

KDEV_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

VERSION = "0.2.0"

BANNER = f"""[bold cyan]
  \u2588\u2588\u2557  \u2588\u2588\u2557\u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557\u2588\u2588\u2557   \u2588\u2588\u2557
  \u2588\u2588\u2551 \u2588\u2588\u2554\u255d\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2550\u2550\u255d\u2588\u2588\u2551   \u2588\u2588\u2551
  \u2588\u2588\u2588\u2588\u2588\u2554\u255d \u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2557  \u2588\u2588\u2551   \u2588\u2588\u2551
  \u2588\u2588\u2554\u2550\u2588\u2588\u2557 \u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u255d  \u255a\u2588\u2588\u2557 \u2588\u2588\u2554\u255d
  \u2588\u2588\u2551  \u2588\u2588\u2557\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u255a\u2588\u2588\u2588\u2588\u2554\u255d
  \u255a\u2550\u255d  \u255a\u2550\u255d\u255a\u2550\u2550\u2550\u2550\u2550\u255d \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u255d  \u255a\u2550\u2550\u2550\u255d  [/bold cyan][dim]v{VERSION}[/dim]
"""


# ══════════════════════════════════════════════════════════════════════════════
#  BedrockBearerModel — calls AWS Bedrock directly via API key (bearer token)
#
#  Why this exists:
#    pydantic-ai's AnthropicModel sends to /v1/messages (Anthropic API format).
#    AWS Bedrock's endpoint is /model/{modelId}/invoke (different URL + body).
#    The Anthropic SDK uses x-api-key header; Bedrock uses Authorization: Bearer.
#    This class bypasses the SDK entirely and speaks Bedrock's protocol directly.
# ══════════════════════════════════════════════════════════════════════════════
class BedrockBearerModel(Model):

    def __init__(self, model_id: str, region: str, token: str):
        self._model_id = model_id
        self._region   = region
        self._token    = token
        self._url      = (
            f"https://bedrock-runtime.{region}.amazonaws.com"
            f"/model/{model_id}/invoke-with-response-stream"
        )

    @property
    def name(self) -> str:
        return f"bedrock-bearer:{self._model_id}"

    @property
    def model_name(self) -> str:
        return self._model_id

    @property
    def system(self) -> str:
        return "bedrock-bearer"

    # ── pydantic-ai messages → Bedrock format ─────────────────────────────────
    def _to_bedrock(
        self, messages: list[ModelMessage]
    ) -> tuple[str, list[dict]]:
        system_parts: list[str] = []
        out: list[dict] = []

        for msg in messages:
            if isinstance(msg, ModelRequest):
                tool_results: list[dict] = []
                user_texts:   list[dict] = []

                for part in msg.parts:
                    if isinstance(part, SystemPromptPart):
                        system_parts.append(part.content)
                    elif isinstance(part, UserPromptPart):
                        if isinstance(part.content, str):
                            user_texts.append({"type": "text", "text": part.content})
                    elif isinstance(part, ToolReturnPart):
                        tool_results.append({
                            "type":        "tool_result",
                            "tool_use_id": part.tool_call_id,
                            "content":     str(part.content),
                        })

                # tool_results MUST be in their own user message immediately
                # after the assistant tool_use — never merged with user text
                if tool_results:
                    out.append({"role": "user", "content": tool_results})
                if user_texts:
                    out.append({"role": "user", "content": user_texts})

            elif isinstance(msg, ModelResponse):
                asst: list[dict] = []
                for part in msg.parts:
                    if isinstance(part, TextPart) and part.content:
                        asst.append({"type": "text", "text": part.content})
                    elif isinstance(part, ToolCallPart):
                        args = (
                            part.args if isinstance(part.args, dict)
                            else json.loads(part.args) if isinstance(part.args, str)
                            else {}
                        )
                        asst.append({
                            "type":  "tool_use",
                            "id":    part.tool_call_id,
                            "name":  part.tool_name,
                            "input": args,
                        })
                if asst:
                    out.append({"role": "assistant", "content": asst})

        # Merge consecutive same-role messages (Bedrock rejects them).
        # CRITICAL: never merge tool_result blocks — Bedrock requires them to
        # appear in their own user message immediately after the assistant
        # tool_use block.  Merging them loses that adjacency guarantee.
        def _has_tool_result(msg: dict) -> bool:
            return any(
                isinstance(p, dict) and p.get("type") == "tool_result"
                for p in msg.get("content", [])
            )

        merged: list[dict] = []
        for m in out:
            can_merge = (
                merged                                    # something to merge into
                and merged[-1]["role"] == m["role"]       # same role
                and not _has_tool_result(merged[-1])      # last msg is NOT tool_result
                and not _has_tool_result(m)               # incoming msg is NOT tool_result
            )
            if can_merge:
                merged[-1]["content"].extend(m["content"])
            else:
                merged.append({"role": m["role"], "content": list(m["content"])})

        return "\n\n".join(system_parts), merged

    def _tools_for_bedrock(self, params: ModelRequestParameters) -> list[dict]:
        result = []
        all_tools = list(getattr(params, "function_tools", None) or [])
        for attr in ("result_tools", "output_tools"):
            all_tools += list(getattr(params, attr, None) or [])
        for t in all_tools:
            result.append({
                "name":         t.name,
                "description":  t.description or "",
                "input_schema": t.parameters_json_schema,
            })
        return result

    # ── AWS Event Stream parser ───────────────────────────────────────────────
    @staticmethod
    def _parse_event(data: bytes) -> tuple[str, dict]:
        """
        Parse one AWS Event Stream binary frame.
        Frame layout:
          [0:4]  total_length      (big-endian uint32)
          [4:8]  headers_length    (big-endian uint32)
          [8:12] prelude_crc       (ignored)
          [12 : 12+headers_length] headers
          [12+headers_length : total_length-4] payload JSON
          [-4:]  message_crc      (ignored)

        Header wire types and their sizes:
          0 = bool_true   (0 bytes)
          1 = bool_false  (0 bytes)
          2 = byte        (1 byte)
          3 = short       (2 bytes)
          4 = int         (4 bytes)
          5 = long        (8 bytes)
          6 = bytes       (2-byte len prefix + N bytes)
          7 = string      (2-byte len prefix + N bytes)
          8 = timestamp   (8 bytes)
          9 = uuid        (16 bytes)
        """
        headers_len = struct.unpack_from(">I", data, 4)[0]
        h_off = 12
        h_end = 12 + headers_len
        event_type = ""
        while h_off < h_end:
            try:
                nlen  = data[h_off]; h_off += 1
                name  = data[h_off:h_off + nlen].decode("utf-8"); h_off += nlen
                vtype = data[h_off]; h_off += 1

                # Advance h_off by the correct amount for each type
                if vtype in (0, 1):        # bool — no value bytes
                    val = str(vtype == 0)
                elif vtype == 2:           # byte
                    val = str(data[h_off]); h_off += 1
                elif vtype == 3:           # short (2 bytes)
                    val = str(struct.unpack_from(">H", data, h_off)[0]); h_off += 2
                elif vtype == 4:           # int (4 bytes)
                    val = str(struct.unpack_from(">I", data, h_off)[0]); h_off += 4
                elif vtype == 5:           # long (8 bytes)
                    val = str(struct.unpack_from(">Q", data, h_off)[0]); h_off += 8
                elif vtype in (6, 7):      # bytes or string — 2-byte length prefix
                    vlen = struct.unpack_from(">H", data, h_off)[0]; h_off += 2
                    raw  = data[h_off:h_off + vlen]; h_off += vlen
                    val  = raw.decode("utf-8", errors="replace") if vtype == 7 else raw.hex()
                elif vtype == 8:           # timestamp (8 bytes)
                    val = str(struct.unpack_from(">Q", data, h_off)[0]); h_off += 8
                elif vtype == 9:           # uuid (16 bytes)
                    val = data[h_off:h_off + 16].hex(); h_off += 16
                else:
                    break  # truly unknown type — bail

                if name == ":event-type":
                    event_type = val
            except Exception:
                break  # malformed header — stop but keep what we have

        payload_start = 12 + headers_len
        payload_end   = len(data) - 4
        try:
            payload = json.loads(data[payload_start:payload_end]) if payload_end > payload_start else {}
        except Exception:
            payload = {}
        return event_type, payload

    # ── Required by pydantic-ai Model ABC ─────────────────────────────────────
    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        *args: Any,
        **kwargs: Any,
    ) -> ModelResponse:
        """
        Stream from Bedrock's invoke-with-response-stream endpoint.
        Text tokens are printed to the terminal as they arrive.
        Tool-use blocks are accumulated silently and shown as ⟳ tool_name.
        Returns a complete ModelResponse once the stream ends.
        """
        system, bedrock_msgs = self._to_bedrock(messages)
        tools = self._tools_for_bedrock(model_request_parameters)

        ms = model_settings or {}
        max_tok = (
            ms.get("max_tokens") if isinstance(ms, dict)
            else getattr(ms, "max_tokens", None)
        ) or 4096

        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens":        max_tok,
            "messages":          bedrock_msgs,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = tools

        if os.getenv("KDEV_DEBUG"):
            console.print(f"[dim]DEBUG → {self._url}[/dim]")
            console.print(f"[dim]DEBUG msgs: {len(bedrock_msgs)}, tools: {len(tools)}[/dim]")

        # content_blocks[index] = {"type": "text", "text": "..."}
        #                       | {"type": "tool_use", "id": ..., "name": ..., "input_json": "..."}
        content_blocks: dict[int, dict] = {}
        buffer    = b""
        has_text  = False
        _think_buf = ""   # accumulates partial <think> blocks for live filtering
        _in_think  = False

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", self._url,
                json=body,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type":  "application/json",
                    "Accept":        "application/vnd.amazon.eventstream",
                },
            ) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    if os.getenv("KDEV_DEBUG"):
                        console.print(f"[dim red]DEBUG ← HTTP {resp.status_code}: {err[:400]}[/dim red]")
                    raise RuntimeError(
                        f"Bedrock HTTP {resp.status_code}: {err[:300].decode('utf-8', errors='replace')}"
                    )

                if os.getenv("KDEV_DEBUG"):
                    console.print(f"[dim]DEBUG ← HTTP {resp.status_code} (streaming)[/dim]")

                import base64 as _base64
                _debug = os.getenv("KDEV_DEBUG")
                _first_frame_dumped = False
                async for chunk in resp.aiter_bytes():
                    buffer += chunk
                    # Consume all complete frames from buffer
                    while len(buffer) >= 12:
                        total_len = struct.unpack_from(">I", buffer, 0)[0]
                        if len(buffer) < total_len:
                            break  # wait for more data
                        frame   = buffer[:total_len]
                        buffer  = buffer[total_len:]

                        # Raw dump of first frame so we can see exact wire format
                        if _debug and not _first_frame_dumped:
                            _first_frame_dumped = True
                            console.print(f"[dim]DEBUG first frame ({len(frame)} bytes) hex: {frame[:80].hex()}[/dim]")
                            console.print(f"[dim]DEBUG first frame ascii: {frame[:80]}[/dim]")

                        event_type, outer_payload = self._parse_event(frame)

                        if _debug:
                            console.print(f"[dim]DEBUG event_type={event_type!r} payload_keys={list(outer_payload.keys())}[/dim]")

                        # Bedrock wraps each Anthropic streaming event in:
                        # outer frame event_type="chunk" → payload={"bytes": "<base64>"}
                        # The base64 decodes to the actual Anthropic event JSON.
                        if event_type == "chunk" and "bytes" in outer_payload:
                            try:
                                inner_bytes = _base64.b64decode(outer_payload["bytes"])
                                payload = json.loads(inner_bytes)
                                event_type = payload.get("type", "")
                                if _debug:
                                    console.print(f"[dim]DEBUG inner event_type={event_type!r}[/dim]")
                            except Exception as _e:
                                if _debug:
                                    console.print(f"[dim red]DEBUG base64 decode failed: {_e}[/dim red]")
                                continue
                        else:
                            payload = outer_payload
                            if event_type not in (
                                "content_block_start", "content_block_delta",
                                "content_block_stop", "message_start",
                                "message_delta", "message_stop",
                            ):
                                continue

                        if event_type == "content_block_start":
                            idx   = payload.get("index", 0)
                            block = payload.get("content_block", {})
                            if block.get("type") == "text":
                                content_blocks[idx] = {"type": "text", "text": ""}
                            elif block.get("type") == "tool_use":
                                content_blocks[idx] = {
                                    "type":       "tool_use",
                                    "id":         block.get("id", ""),
                                    "name":       block.get("name", ""),
                                    "input_json": "",
                                }

                        elif event_type == "content_block_delta":
                            idx   = payload.get("index", 0)
                            delta = payload.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if idx in content_blocks:
                                    content_blocks[idx]["text"] += text
                                # Buffer think blocks — print dimmed, print answer normally
                                if "<think>" in _think_buf + text or _in_think:
                                    _think_buf += text
                                    # Detect open/close
                                    if not _in_think and "<think>" in _think_buf:
                                        _in_think = True
                                        # Print anything before <think>
                                        pre = _think_buf[:_think_buf.index("<think>")]
                                        if pre:
                                            print(pre, end="", flush=True)
                                        _think_buf = _think_buf[_think_buf.index("<think>"):]
                                    if _in_think and "</think>" in _think_buf:
                                        _in_think = False
                                        inner = _think_buf[7:_think_buf.index("</think>")]
                                        first_line = inner.strip().split("\n")[0][:60]
                                        console.print(f"[dim]◌ {first_line}…[/dim]")
                                        post = _think_buf[_think_buf.index("</think>")+8:]
                                        _think_buf = ""
                                        if post:
                                            print(post, end="", flush=True)
                                            has_text = True
                                    elif not _in_think:
                                        print(_think_buf, end="", flush=True)
                                        _think_buf = ""
                                        has_text = True
                                else:
                                    print(text, end="", flush=True)
                                    has_text = True
                            elif delta.get("type") == "input_json_delta":
                                if idx in content_blocks:
                                    content_blocks[idx]["input_json"] += delta.get("partial_json", "")

                        elif event_type == "content_block_stop":
                            idx = payload.get("index", 0)
                            # Show tool call indicator when its block closes
                            if idx in content_blocks and content_blocks[idx]["type"] == "tool_use":
                                name = content_blocks[idx]["name"]
                                console.print(f"[dim cyan]⟳ {name}[/dim cyan]")

        if has_text:
            print()  # final newline after streamed text

        # Build pydantic-ai parts from accumulated content blocks
        if os.getenv("KDEV_DEBUG"):
            console.print(f"[dim]DEBUG content_blocks after stream: {content_blocks}[/dim]")

        parts: list = []
        for idx in sorted(content_blocks.keys()):
            blk = content_blocks[idx]
            if blk["type"] == "text" and blk["text"]:
                parts.append(TextPart(content=blk["text"]))
            elif blk["type"] == "tool_use":
                try:
                    args = json.loads(blk["input_json"]) if blk["input_json"] else {}
                except Exception:
                    args = {}
                parts.append(ToolCallPart(
                    tool_name=blk["name"],
                    args=args,
                    tool_call_id=blk["id"],
                ))

        return ModelResponse(
            parts=parts,
            model_name=self._model_id,
            timestamp=datetime.now(tz=timezone.utc),
        )


def messages_to_json(messages: list) -> list:
    """Serialize pydantic-ai messages to JSON-safe dicts."""
    try:
        import json
        return json.loads(ModelMessagesTypeAdapter.dump_json(messages))
    except Exception:
        return []  # non-fatal, session just won't be saved


# ══════════════════════════════════════════════════════════════════════════════
#  Backend selection
# ══════════════════════════════════════════════════════════════════════════════
def build_model() -> "tuple[Model, bool]":
    """
    Returns (model, is_bedrock).
    is_bedrock=True  → BedrockBearerModel streams tokens live inside request(),
                       the agent loop must NOT print result.output again.
    is_bedrock=False → pydantic-ai buffers the full response internally,
                       the agent loop MUST print result.output after agent.run().
    """
    ollama_url   = os.getenv("OLLAMA_BASE_URL", "").strip()
    ollama_model = os.getenv("OLLAMA_MODEL", "").strip()

    # ── 1. Local Ollama ────────────────────────────────────────────────────────
    if ollama_url and ollama_model:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        # OpenAIProvider handles the dummy-key requirement automatically
        # when base_url is set and OPENAI_API_KEY is not in env.
        provider = OpenAIProvider(
            base_url=f"{ollama_url.rstrip('/')}/v1",
            api_key="ollama",
        )
        console.print(f"[dim]Backend: Local Ollama ({ollama_model})[/dim]")
        return OpenAIChatModel(ollama_model, provider=provider), False

    # ── 2. AWS Bedrock ─────────────────────────────────────────────────────────
    bedrock_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "").strip()
    if bedrock_token and bedrock_token != "YOUR_BEARER_TOKEN_HERE":
        bedrock_region = os.getenv("AWS_REGION", "us-east-1")
        bedrock_model  = os.getenv(
            "ANTHROPIC_DEFAULT_SONNET_MODEL", "us.anthropic.claude-sonnet-4-6"
        )
        console.print(f"[dim]Backend: AWS Bedrock ({bedrock_model})[/dim]")
        return BedrockBearerModel(bedrock_model, bedrock_region, bedrock_token), True

    # ── 3. Anthropic direct ────────────────────────────────────────────────────
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if anthropic_key:
        from pydantic_ai.models.anthropic import AnthropicModel
        console.print("[dim]Backend: Anthropic direct API[/dim]")
        return AnthropicModel("claude-sonnet-4-6", api_key=anthropic_key), False

    console.print("[bold red]ERROR: No LLM backend configured.[/bold red]")
    console.print("  Set one of these in .env:")
    console.print("  OLLAMA_BASE_URL=http://localhost:11434  +  OLLAMA_MODEL=<name>")
    console.print("  AWS_BEARER_TOKEN_BEDROCK=...")
    console.print("  ANTHROPIC_API_KEY=sk-ant-...")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
#  Memory / sessions / MCP / commands
# ══════════════════════════════════════════════════════════════════════════════
def load_memory() -> str:
    parts = []
    if USER_MEMORY.exists():
        parts.append(f"# User Memory\n{USER_MEMORY.read_text(encoding='utf-8')}")
    if MEMORY_FILE.exists():
        parts.append(f"# Workspace Memory\n{MEMORY_FILE.read_text(encoding='utf-8')}")
    return "\n\n".join(parts) if parts else ""


def save_session(session_id: str, messages: list, title: str = ""):
    path = SESSIONS_DIR / session_id
    path.mkdir(parents=True, exist_ok=True)
    data = {
        "session_id": session_id,
        "title":      title or "Unnamed session",
        "workspace":  str(Path.cwd()),
        "updated_at": datetime.now().isoformat(),
        "messages":   messages,
    }
    (path / "context.json").write_text(json.dumps(data, indent=2, default=str))


def get_mcp_servers() -> list[MCPServerStdio]:
    """
    Returns all active MCP servers:
      1. nautilus  — file/shell tools (from rovodev)
      2. github    — repo/PR/issue tools (if GITHUB_TOKEN is set)
    """
    servers: list[MCPServerStdio] = []

    # ── nautilus (file + shell tools) ─────────────────────────────────────────
    nautilus_exe = Path(
        r"C:\Users\Kristian\.rovodev\.local\share\acli\1.3.13-stable"
        r"\plugin\rovodev\atlassian_cli_rovodev.exe"
    )
    if nautilus_exe.exists():
        servers.append(MCPServerStdio(
            command=str(nautilus_exe),
            timeout=30,   # Windows startup can be slow
            args=[
                "nautilus", "run",
                "--tools",
                "open_files,create_file,delete_file,move_file,"
                "expand_code_chunks,find_and_replace_code,grep,"
                "expand_folder,bash,powershell,update_allowed_external_paths",
                "--workspace-args-json",
                json.dumps({
                    "workspace_view_max_files": 1000,
                    "allowed_external_paths":   [],
                    "run_shell_in_sandbox":     False,
                }),
            ],
        ))
    else:
        console.print("[yellow]nautilus exe not found — file/shell tools unavailable[/yellow]")
        # ── filesystem MCP (Linux only) ───────────────────────────────────────
        if sys.platform != "win32":
            import shutil as _shutil
            if _shutil.which("npx"):
                servers.append(MCPServerStdio(
                    command="npx",
                    args=["@modelcontextprotocol/server-filesystem", "/home/yanflare"],
                ))
                console.print("[dim]Filesystem MCP: enabled (/home/yanflare)[/dim]")
            else:
                console.print("[yellow]Filesystem MCP: npx not found — install Node.js to enable[/yellow]")

    # ── GitHub MCP (repo, PR, issues, code search) ────────────────────────────
    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    if github_token and github_token != "YOUR_GITHUB_TOKEN_HERE":
        # Only add if the package is already installed globally (avoids npx download timeout)
        import shutil, subprocess
        npx_path = shutil.which("npx")
        if npx_path:
            try:
                result = subprocess.run(
                    ["npm", "list", "-g", "@modelcontextprotocol/server-github", "--depth=0"],
                    capture_output=True, text=True, timeout=5
                )
                pkg_ready = "@modelcontextprotocol/server-github" in result.stdout
            except Exception:
                pkg_ready = False

            if pkg_ready:
                servers.append(MCPServerStdio(
                    command="npx",
                    args=["@modelcontextprotocol/server-github"],  # no -y = no download
                    env={**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": github_token},
                ))
                console.print("[dim]GitHub MCP: enabled[/dim]")
            else:
                console.print("[yellow]GitHub MCP: package not installed.[/yellow]")
                console.print("[dim]  Run: npm install -g @modelcontextprotocol/server-github[/dim]")
        else:
            console.print("[yellow]GitHub MCP: npx not found — install Node.js to enable[/yellow]")

    return servers


def print_help():
    console.print(Panel(
        "\n".join([
            "[bold]/help[/bold]      — show this",
            "[bold]/clear[/bold]     — clear session history",
            "[bold]/memory[/bold]    — open workspace memory file (.agent.md)",
            "[bold]/sessions[/bold]  — list recent sessions",
            "[bold]/skills[/bold]    — list all learned skill documents",
            "[bold]/compress[/bold]  — distill this session into compressed memory",
            "[bold]/exit[/bold]      — quit  (also: q, quit, exit)",
            "",
            "[dim]# <note>[/dim]    — add a quick note to memory",
        ]),
        title="[bold]KDev Commands[/bold]",
        border_style="cyan",
    ))


def handle_command(
    cmd: str, session_id: str, message_history: list
) -> tuple[str | None, list, str]:
    cmd = cmd.strip()

    if cmd in ("exit", "quit", "q", "/exit", "/quit", "/q"):
        console.print("\n[dim]Goodbye.[/dim]")
        sys.exit(0)

    if cmd in ("/help", "/?"):
        print_help()
        return None, message_history, session_id

    if cmd == "/clear":
        console.print("[dim]Session cleared.[/dim]")
        return None, [], str(uuid.uuid4())

    if cmd == "/memory":
        MEMORY_FILE.touch(exist_ok=True)
        import platform as _platform, subprocess as _sp
        try:
            if _platform.system() == "Windows":
                os.startfile(str(MEMORY_FILE))
            elif _platform.system() == "Darwin":
                _sp.Popen(["open", str(MEMORY_FILE)])
            else:
                try:
                    _sp.Popen(["xdg-open", str(MEMORY_FILE)])
                except FileNotFoundError:
                    console.print(f"[dim]No GUI detected. Edit with: nano {MEMORY_FILE}[/dim]")
        except Exception:
            console.print(f"[dim]Memory file: {MEMORY_FILE}[/dim]")
        console.print(f"[dim]Opened {MEMORY_FILE}[/dim]")
        return None, message_history, session_id

    if cmd == "/sessions":
        cwd = str(Path.cwd())
        sessions = []
        for p in SESSIONS_DIR.iterdir():
            ctx = p / "context.json"
            if ctx.exists():
                try:
                    d = json.loads(ctx.read_text())
                    if d.get("workspace") == cwd:
                        sessions.append(d)
                except Exception:
                    pass
        sessions.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        if not sessions:
            console.print("[dim]No sessions for this workspace.[/dim]")
        else:
            for i, s in enumerate(sessions[:10]):
                console.print(
                    f"  [{i+1}] [cyan]{s.get('title','?')}[/cyan]"
                    f" — {s.get('updated_at','?')[:16]}"
                )
        return None, message_history, session_id

    if cmd.startswith("# "):
        note = cmd[2:].strip()
        MEMORY_FILE.parent.mkdir(exist_ok=True)
        with open(MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n- {note}")
        console.print(f"[dim]Note saved.[/dim]")
        return None, message_history, session_id

    if cmd == "/skills":
        skills = list_skills()
        if not skills:
            console.print("[dim]No skills learned yet. Skills are written automatically after complex tasks.[/dim]")
        else:
            from rich.table import Table
            t = Table(title="Learned Skills", border_style="cyan", show_lines=False)
            t.add_column("#",       style="dim", width=3)
            t.add_column("Title",   style="bold cyan")
            t.add_column("Summary", style="white")
            t.add_column("Tags",    style="dim")
            for i, s in enumerate(skills[:20], 1):
                t.add_row(str(i), s["title"], s["summary"][:60], s["tags"][:30])
            console.print(t)
        return None, message_history, session_id

    if cmd == "/compress":
        if not message_history:
            console.print("[dim]Nothing to compress yet.[/dim]")
        else:
            # Signal the async loop to run compression after returning
            # We return a special sentinel message "__COMPRESS__"
            return "__COMPRESS__", message_history, session_id
        return None, message_history, session_id

    return cmd, message_history, session_id


SYSTEM_PROMPT = """\
You are an expert coding assistant running locally on the user's machine.
You have access to file system tools — use them ONLY when the task requires it.
NEVER read .agent.md, context files, or skill files before acting — your memory is already loaded at startup.
NEVER use open_files or expand_code_chunks unless the task explicitly needs file content.
When making changes: make minimal targeted edits, verify the result.
Be concise. Don't explain what you're about to do — just do it.
Issue ONE tool call at a time. Wait for result before the next call.
Working directory: {cwd}
{memory}
{skills}"""

SYSTEM_PROMPT_THINKING = """\
You are an expert coding assistant running locally on the user's machine.
You have access to file system tools — use them ONLY when the task requires it.
NEVER read .agent.md, context files, or skill files before acting — your memory is already loaded at startup.
NEVER use open_files or expand_code_chunks unless the task explicitly needs file content.
When making changes: make minimal targeted edits, verify the result.
Be concise. Don't explain what you're about to do — just do it.
Issue ONE tool call at a time. Wait for result before the next call.
Working directory: {cwd}
{memory}
{skills}

You have extended reasoning. Use <think>...</think> to reason internally before responding.
After </think>, give only the final concise answer or tool call — no thinking in output."""



def is_thinking_model(model_name: str) -> bool:
    name = model_name.lower()
    return any(k in name for k in ("qwen3", "qwen2.5", "deepseek-r1", "qwq", "thinking", "reasoner", "r1"))


def strip_think_blocks(text: str) -> str:
    import re
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


# ══════════════════════════════════════════════════════════════════════════════
#  Main agent loop
#  NOTE: Uses agent.run() (not run_stream) because BedrockBearerModel is
#  non-streaming. Tool calls run internally; shown after completion.
# ══════════════════════════════════════════════════════════════════════════════
async def run_agent_loop(initial_message: str | None = None, pipe_mode: bool = False):
    # pipe_mode: stdin is a pipe (from kdev_web.py). Use readline() not prompt_toolkit.
    # Print ##KDEV_DONE## after each response as a sentinel.
    model, _is_bedrock = build_model()
    mcp_servers = get_mcp_servers()
    memory     = load_memory()
    skills_ctx  = load_relevant_skills("")   # will be refreshed per-message
    ollama_model_name = os.getenv("OLLAMA_MODEL", "")
    base_prompt = SYSTEM_PROMPT_THINKING if is_thinking_model(ollama_model_name) else SYSTEM_PROMPT
    if is_thinking_model(ollama_model_name):
        console.print(f"[dim]Thinking model detected ({ollama_model_name}) — chain-of-thought enabled[/dim]")
    system      = base_prompt.format(cwd=Path.cwd(), memory=memory, skills=skills_ctx)
    session_id = str(uuid.uuid4())
    message_history: list = []

    agent = Agent(
        model=model,
        output_type=str,
        system_prompt=system,
        mcp_servers=mcp_servers,
        retries=3,
    )

    pt_session = None
    if not pipe_mode:
        pt_session = PTSession(
            history=FileHistory(str(HISTORY_FILE)),
            auto_suggest=AutoSuggestFromHistory(),
        )

    if not pipe_mode:
        console.print(BANNER)
        console.print(f"Working in [bold blue]{Path.cwd()}[/bold blue]\n")

    # ── MCP startup with graceful degradation ────────────────────────────────
    # anyio wraps errors in ExceptionGroup which requires BaseExceptionGroup catch
    # Strategy: try all → try nautilus-only → try no MCP
    active_servers = mcp_servers
    mcp_ctx = None

    for attempt, servers in [
        ("all",      mcp_servers),
        ("nautilus", [s for s in mcp_servers if "rovodev" in str(getattr(s, "command", ""))]),
        ("none",     []),
    ]:
        try:
            _agent = Agent(model=model, output_type=str, system_prompt=system, mcp_servers=servers, retries=3)
            _ctx   = _agent.run_mcp_servers()
            await _ctx.__aenter__()
            agent          = _agent
            mcp_ctx        = _ctx
            active_servers = servers
            break
        except* TimeoutError:
            if attempt == "all" and len(servers) > 1:
                console.print("[yellow]⚠ MCP timeout — retrying with nautilus only[/yellow]")
            elif attempt == "nautilus" and servers:
                console.print("[yellow]⚠ nautilus also timed out — running without MCP tools[/yellow]")
        except* Exception as eg:
            errs = ", ".join(type(e).__name__ for e in eg.exceptions)
            if attempt == "all":
                console.print(f"[yellow]⚠ MCP error ({errs}) — retrying with nautilus only[/yellow]")
            elif attempt == "nautilus":
                console.print(f"[yellow]⚠ MCP unavailable ({errs}) — running without tools[/yellow]")

    if mcp_ctx is None:
        # Last resort: no MCP at all
        agent   = Agent(model=model, output_type=str, system_prompt=system, mcp_servers=[], retries=3)
        mcp_ctx = agent.run_mcp_servers()
        await mcp_ctx.__aenter__()

    if active_servers:
        labels = []
        for s in active_servers:
            cmd = str(getattr(s, "command", ""))
            args = str(getattr(s, "args", ""))
            if "rovodev" in cmd:
                labels.append("nautilus")
            elif "github" in args:
                labels.append("github")
        console.print(f"[green]\u2713[/green] MCP tools ready ({', '.join(labels) or 'active'})\n")
    else:
        console.print("[yellow]Running without MCP tools — file/shell operations unavailable[/yellow]\n")

    try:
        first_message = initial_message

        while True:
            # ── Input ─────────────────────────────────────────────────────────
            if first_message:
                user_input    = first_message
                first_message = None
            elif pipe_mode:
                # Non-TTY pipe input: read one line from stdin via thread executor
                try:
                    loop = asyncio.get_event_loop()
                    user_input = await loop.run_in_executor(None, sys.stdin.readline)
                    if not user_input:  # EOF — web server closed the pipe
                        break
                    user_input = user_input.rstrip("\n")
                except Exception:
                    break
            else:
                try:
                    user_input = await pt_session.prompt_async("> ", completer=None)
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[dim]Use /exit to quit.[/dim]")
                    continue

            user_input = user_input.strip()
            if not user_input:
                continue

            # ── Commands ──────────────────────────────────────────────────────
            message_to_send, message_history, session_id = handle_command(
                user_input, session_id, message_history
            )
            if message_to_send is None:
                continue

            # ── /compress sentinel ────────────────────────────────────────
            if message_to_send == "__COMPRESS__":
                console.print("[dim]Distilling session with knowledge compression…[/dim]\n")
                try:
                    result_c = await compress_session(
                        message_history, str(Path.cwd()), session_id
                    )
                    if "error" in result_c:
                        console.print(f"[red]{result_c['error']}[/red]")
                    else:
                        console.print(Markdown(result_c["summary"]))
                        console.print(f"\n[dim]Saved → {result_c['file_path']}[/dim]")
                        if result_c.get("memory_update"):
                            console.print("\n[bold cyan]Append to .agent.md?[/bold cyan] (y/n): ", end="")
                            try:
                                choice = input().strip().lower()
                                if choice == "y":
                                    MEMORY_FILE.parent.mkdir(exist_ok=True)
                                    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                                        f.write(f"\n\n## Session {datetime.now().strftime('%Y-%m-%d')}\n")
                                        f.write(result_c["memory_update"])
                                    console.print("[dim]Memory updated. ✓[/dim]")
                            except Exception:
                                pass
                except Exception as e:
                    console.print(f"[red]Compression error: {e}[/red]")
                continue

            # ── Run (streaming) ───────────────────────────────────────────
            console.print()
            try:
                # Text streams live to terminal inside BedrockBearerModel.request()
                # Tool call indicators (⟳ name) print on content_block_stop
                # Nothing to print here after the fact — it already appeared live
                # Inject relevant skills into this specific request via message prefix
                task_skills = load_relevant_skills(message_to_send)
                augmented_msg = message_to_send
                if task_skills:
                    augmented_msg = message_to_send + f"\n\n<skills_context>\n{task_skills}\n</skills_context>"

                if os.getenv("KDEV_DEBUG"):
                    print(f"DEBUG: calling agent.run(), is_bedrock={_is_bedrock}", flush=True)

                result = await agent.run(
                    augmented_msg,
                    message_history=message_history,
                )

                _output = getattr(result, 'output', None) or getattr(result, 'data', '') or ''

                if os.getenv("KDEV_DEBUG"):
                    print(f"DEBUG: agent.run() done. output length={len(_output)}", flush=True)
                    print(f"DEBUG: output preview={repr(_output[:120])}", flush=True)

                # Bedrock streams tokens live inside BedrockBearerModel.request()
                # so nothing to print. All other backends buffer the full response
                # and we must print it here.
                if not _is_bedrock:
                    import re as _re_think
                    think_blocks = _re_think.findall(
                        r'<think>(.*?)</think>', _output, _re_think.DOTALL
                    )
                    clean = _re_think.sub(
                        r'<think>.*?</think>', '', _output, flags=_re_think.DOTALL
                    ).strip()
                    # Show first line of reasoning dimmed
                    if think_blocks:
                        first = think_blocks[0].strip().split('\n')[0][:80]
                        console.print(f"[dim]◌ {first}…[/dim]")
                    # Print the clean answer
                    if clean:
                        console.print(Markdown(clean))
                    elif _output.strip():
                        # No think blocks or stripping emptied it — print raw
                        console.print(Markdown(_output.strip()))
                    else:
                        console.print("[yellow]⚠ Model returned empty response[/yellow]")

                new_msgs = list(result.new_messages())
                message_history = message_history + new_msgs

                # ── Trace analysis + skill writing ────────────────────────
                trace = analyze_trace(new_msgs)
                if trace.is_complex:
                    import asyncio as _aio
                    skill_path = await maybe_write_skill(
                        message_to_send, new_msgs, trace
                    )
                    if skill_path:
                        console.print(f"[dim green]✦ Skill learned → {Path(skill_path).name}[/dim green]")

            except KeyboardInterrupt:
                console.print("\n[yellow]\u2298 Interrupted[/yellow]")
                if pipe_mode:
                    print("##KDEV_DONE##", flush=True)
                continue
            except UnexpectedModelBehavior as e:
                msg_str = str(e)
                if "retries" in msg_str.lower() or "validation" in msg_str.lower():
                    console.print(
                        "\n[yellow]⚠ Model produced an unexpected response format — "
                        "the task may have partially completed. Try rephrasing or check results.[/yellow]"
                    )
                else:
                    console.print(f"\n[red]Model error: {e}[/red]")
                if os.getenv("KDEV_DEBUG"):
                    import traceback; traceback.print_exc()
                if pipe_mode:
                    print("##KDEV_DONE##", flush=True)
                continue
            except Exception as e:
                err_str = str(e)
                # ── Friendly messages for known interruption causes ────────
                if "getaddrinfo" in err_str or "Name or service not known" in err_str:
                    console.print(
                        "\n[yellow]⚠ DNS/network failure — Bedrock bearer token likely expired.[/yellow]"
                    )
                    console.print("[dim]  Refresh AWS_BEARER_TOKEN_BEDROCK in .env and restart kdev.[/dim]")
                elif "429" in err_str or "Too many requests" in err_str:
                    console.print(
                        "\n[yellow]⚠ Bedrock rate limit hit (HTTP 429).[/yellow]"
                    )
                    console.print("[dim]  Wait ~60s then continue. For long tasks, break them into smaller steps.[/dim]")
                elif "400" in err_str and "tool_use" in err_str:
                    console.print(
                        "\n[yellow]⚠ Bedrock message ordering error (HTTP 400).[/yellow]"
                    )
                    console.print("[dim]  This is a known pydantic-ai issue. Use /clear to reset history and retry.[/dim]")
                else:
                    import traceback as _tb
                    tb_str = _tb.format_exc()
                    console.print(f"\n[red]Error: {e}[/red]")
                    console.print("[dim]⟳ self-diagnosing…[/dim]")
                    try:
                        diagnosis = await self_debug_error(
                            error=e,
                            traceback_str=tb_str,
                            user_task=message_to_send,
                            message_history=message_history,
                        )
                        if diagnosis:
                            console.print(Panel(
                                Markdown(diagnosis),
                                title="[bold yellow]⚕ Auto-diagnosis[/bold yellow]",
                                border_style="yellow",
                            ))
                    except Exception:
                        pass
                    if os.getenv("KDEV_DEBUG"):
                        _tb.print_exc()
                if pipe_mode:
                    print("##KDEV_DONE##", flush=True)
                continue

            # Auto-save session
            save_session(
                session_id,
                messages_to_json(message_history),
                title=user_input[:60],
            )
            if pipe_mode:
                print("##KDEV_DONE##", flush=True)
            else:
                console.print()

            if initial_message:
                break
    finally:
        try:
            await mcp_ctx.__aexit__(None, None, None)
        except Exception:
            pass


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    if msg and msg.strip().startswith("/"):
        console.print(f"[yellow]'{msg.strip()}' is a REPL command — start kdev normally and type it at the > prompt.[/yellow]")
        sys.exit(0)
    pipe_mode = "--pipe-mode" in sys.argv
    try:
        asyncio.run(run_agent_loop(initial_message=msg, pipe_mode=pipe_mode))
    except KeyboardInterrupt:
        console.print("\n[dim]Goodbye.[/dim]")
