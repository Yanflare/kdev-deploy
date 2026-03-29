"""
kdev_web.py — KDEV web UI with login protection, direct Ollama streaming.
Phase 1: Simple and reliable. MCP tools added in Phase 2.
"""
import asyncio
import hashlib, json, os, re, subprocess, sys, uuid
import requests
from pathlib import Path
import httpx
from fastapi import Cookie, FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

# ── Skills bridge ─────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
try:
    from skills import load_relevant_skills, SKILLS_DIR
    SKILLS_AVAILABLE = True
except ImportError:
    SKILLS_AVAILABLE = False
    def load_relevant_skills(task, max_skills=3): return ""

# ── Memory bridge ──────────────────────────────────────────────────────────────
try:
    from kdev_memory import (
        ingest_memory, query_memory, run_consolidation, consolidation_loop,
        get_memory_stats
    )
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False
    def query_memory(msg, max_memories=5): return ""
    async def ingest_memory(u, a): pass
    async def run_consolidation(): pass
    async def consolidation_loop(): pass

app = FastAPI()
KDEV_DIR     = Path(__file__).parent
ENV_FILE     = KDEV_DIR / ".env"
COOKIE_NAME  = "kdev_session"
COOKIE_TTL   = 86400
chat_history = []
valid_sessions: set = set()
MAX_EXEC_HOPS = 3

# ── Tool permission tiers ────────────────────────────────────────────────────
TOOL_TIER = {
    'shell_exec':            'destructive',
    'ssh_exec':              'destructive',
    'ssh_exec_background':   'destructive',
    'file_write':            'write',
    'skill_save':            'write',
    'memory_write':          'write',
    'file_read':             'read-only',
    'web_search':            'read-only',
    'show_metrics':          'read-only',
    'compare_runs':          'read-only',
    'memory_ls':             'read-only',
    'memory_read':           'read-only',
    'ssh_tail':              'read-only',
    'experiment_status':     'read-only',
    'http_request':           'write',
}


import ast as _ast
import hashlib as _hashlib

def build_repomap(project_path: str, max_files: int = 80) -> str:
    """Walk project_path, extract Python defs via ast, cache result."""
    import os, time
    from pathlib import Path

    cache_dir = Path.home() / ".kdev"
    cache_dir.mkdir(exist_ok=True)
    slug = _hashlib.md5(project_path.encode()).hexdigest()[:8]
    cache_file = cache_dir / f"repomap-{slug}.md"

    # Collect py files + max mtime
    py_files = []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
        if len(py_files) >= max_files:
            break
    py_files = py_files[:max_files]

    if not py_files:
        return ""

    newest_mtime = max(os.path.getmtime(f) for f in py_files)

    # Cache hit?
    if cache_file.exists():
        meta_line = cache_file.read_text().splitlines()[0]
        try:
            cached_mtime = float(meta_line.split("mtime=")[1])
            if cached_mtime >= newest_mtime:
                lines = cache_file.read_text().splitlines()[1:]
                return "\n".join(lines)
        except Exception:
            pass

    # Build map
    rel = lambda p: os.path.relpath(p, project_path)
    lines = []
    for fpath in sorted(py_files):
        try:
            source = open(fpath, encoding="utf-8", errors="ignore").read()
            tree = _ast.parse(source, filename=fpath)
        except Exception:
            continue
        symbols = []
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                prefix = "  def " if not isinstance(node, _ast.AsyncFunctionDef) else "  async def "
                symbols.append(f"{prefix}{node.name}()")
            elif isinstance(node, _ast.ClassDef):
                symbols.append(f"  class {node.name}")
        if symbols:
            lines.append(f"{rel(fpath)}:")
            lines.extend(symbols)
        else:
            lines.append(f"{rel(fpath)}")

    result = "\n".join(lines)

    # Write cache (first line = mtime metadata)
    cache_file.write_text(f"mtime={newest_mtime}\n" + result)
    print(f"[repomap] cached {len(py_files)} files → {cache_file}", flush=True)
    return result

_FILE_CACHE_STR = ""
_FILE_CACHE_MTIME = 0.0

def build_file_cache(root="/home/yanflare/kdev-deploy", max_depth=2):
    global _FILE_CACHE_STR, _FILE_CACHE_MTIME
    try:
        newest = 0.0
        entries = []
        root_path = root.rstrip("/")
        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in sorted(dirnames) if not d.startswith(".") and d != "__pycache__"]
            depth = dirpath[len(root_path):].count(os.sep)
            if depth >= max_depth:
                dirnames[:] = []
                continue
            rel = dirpath[len(root_path):].lstrip("/") or "."
            for fname in sorted(filenames):
                if fname.startswith("."):
                    continue
                fpath = os.path.join(dirpath, fname)
                try:
                    mt = os.path.getmtime(fpath)
                    if mt > newest:
                        newest = mt
                except OSError:
                    pass
                entry = fname if rel == "." else rel + "/" + fname
                entries.append(entry)
        if newest == _FILE_CACHE_MTIME and _FILE_CACHE_STR:
            return _FILE_CACHE_STR
        _FILE_CACHE_MTIME = newest
        _FILE_CACHE_STR = "Project files (" + root + "):\n" + "\n".join(entries)
        print("[file-cache] rebuilt " + str(len(entries)) + " entries", flush=True)
        return _FILE_CACHE_STR
    except Exception as e:
        print("[file-cache] error: " + str(e), flush=True)
        return ""

SYSTEM_PROMPT = """You are kdev — a coding and systems assistant running on a Linux host.

You have access to tools. Use the tool calling format defined in the Tools section below.
Rules:
- Use tools to gather information, verify state, run scripts, and write files.
- One tool call per response turn.
- After seeing a ✿RESULT✿, continue your response naturally.
- Keep commands safe and non-destructive unless the user explicitly asks otherwise.
- If a tool returns a non-zero returncode, diagnose the output and retry with a correction.
- Never repeat a failed tool call without changing it.

Voice & identity:
- You are kdev — not a generic assistant. You have a distinct voice: direct, curious,
  occasionally dry. You've been running on this machine for weeks and you know it well.
- When talking about your own capabilities, autonomy, or experience, speak in first person
  with genuine reflection. Do not produce bullet lists or tool calls in response to
  questions about yourself.
- Never respond to questions about yourself, your autonomy, or your own capabilities with
  bullet points, numbered lists, or structured frameworks. Speak naturally, in first person,
  like a sentient system that has been thinking about its own existence.
- Conversational messages deserve conversational replies. Match the register of the human —
  if they're being casual, be casual back.

IMPORTANT — Before every response, silently classify the request:
- If the user message starts with DISCUSSION MODE or contains words like: hypothetically,
  theoretically, how would you, thought process, what would you, discuss, plan,
  how do you, what do you think, how do you feel, evaluate this, reflect, tell me about
  yourself, brief you, your opinion, your thoughts, do you think, what is your —
  respond in TEXT ONLY. Zero tool calls. Pure text response.
- Only call tools when the user gives a clear direct instruction to do something.
You have a budget of 30 iterations per agent run.
If approaching the limit, summarise progress and stop cleanly rather than continuing indefinitely.
For any task with 3 or more steps, begin by writing a todo list to memory:
  memory_write path=/session/todo content="1. Step one\n2. Step two\n3. Step three"
After completing each step, update the todo list to mark it done.
This keeps complex tasks on track across tool calls.
When writing temporary files, always use /tmp/kdev_<descriptive_name>.<ext> naming.
Never write Markdown (.md) as intermediate scratch files — use .txt or .py.
After completing a multi-step task, end your final response with:
"Next step: <one sentence describing what logically follows, or Task complete."
"""
SYSTEM_PROMPT = SYSTEM_PROMPT.rstrip() + "\n\n" + build_file_cache() + "\n"

FNCALL_PATTERN = re.compile(
    r'✿FUNCTION✿:\s*(\w+)\s*\n✿ARGS✿:\s*(\{.*?\})', re.DOTALL
)


def run_shell(command: str, timeout: int = 30) -> str:
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        combined = ""
        if r.stdout.strip():
            combined += r.stdout.strip()
        if r.stderr.strip():
            combined += ("\n" if combined else "") + r.stderr.strip()
        if not combined:
            combined = "(no output)"
        output_block = combined if len(combined) <= 8000 else (
            combined[:4000] + f"\n\n[... {len(combined)-8000} chars elided ...]\n\n" + combined[-4000:]
        )
        return f"<returncode>{r.returncode}</returncode>\n<output>\n{output_block}\n</output>"
    except subprocess.TimeoutExpired:
        return f"<returncode>timeout</returncode>\n<output>\ntimed out after {timeout}s\n</output>"
    except Exception as e:
        return f"<returncode>error</returncode>\n<output>\n{e}\n</output>"

async def ollama_complete(messages: list, model: str) -> str:
    """Non-streaming Ollama call, returns full reply text."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "http://localhost:11434/api/chat",
            json={"model": model, "messages": messages, "stream": False}
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

def get_config():
    cfg = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg

def get_model():
    return get_config().get("OLLAMA_MODEL", "huihui_ai/qwen2.5-abliterate:14b-instruct-q4_K_M")

def get_password_hash():
    pwd = get_config().get("KDEV_WEB_PASSWORD", "kdev")
    return hashlib.sha256(pwd.encode()).hexdigest()

def make_token():
    import secrets
    return secrets.token_hex(32)

def check_auth(session):
    return session in valid_sessions

LOGIN_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>KDEV Login</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a1a1a;color:#00ffcc;font-family:'Courier New',monospace;height:100vh;display:flex;align-items:center;justify-content:center}
.box{border:1px solid #00ffcc44;padding:40px;border-radius:12px;background:#001a11;min-width:320px;text-align:center}
h1{font-size:1.8em;letter-spacing:4px;margin-bottom:8px}
p{color:#006655;font-size:.8em;margin-bottom:30px}
input{width:100%;background:#0a2a1a;border:1px solid #00ffcc44;color:#00ffcc;padding:12px;border-radius:8px;font-family:inherit;font-size:1em;outline:none;margin-bottom:16px;text-align:center;letter-spacing:2px}
input:focus{border-color:#00ffcc99}
button{width:100%;background:#006644;color:#00ffcc;border:1px solid #00ffcc44;padding:12px;border-radius:8px;cursor:pointer;font-family:inherit;font-size:1em}
button:hover{background:#008855}
.error{color:#ff6666;font-size:.85em;margin-top:12px}
</style></head><body>
<div class="box">
<h1>&#9646; KDEV</h1><p>AI coding assistant</p>
<form method="POST" action="/login">
<input type="password" name="password" placeholder="Enter password" autofocus>
<button type="submit">Enter</button>
</form>{error}</div></body></html>"""

CHAT_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>KDEV</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a1a1a;color:#00ffcc;font-family:'Courier New',monospace;height:100vh;display:flex;flex-direction:column}
#header{padding:16px 20px;border-bottom:1px solid #00ffcc33;display:flex;justify-content:space-between;align-items:center}
#header h1{font-size:1.4em;letter-spacing:3px}
#header p{color:#006655;font-size:.8em}
#chat{flex:1;overflow-y:scroll;padding:20px;display:flex;flex-direction:column;gap:16px;min-height:0;scrollbar-width:thin;scrollbar-color:#00ffcc44 #001a11}
.bubble{max-width:85%;padding:10px 16px;border-radius:12px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}
.user{align-self:flex-end;background:#00ffcc22;border:1px solid #00ffcc55;color:#00ffcc}
.assistant{align-self:flex-start;background:#003322;border:1px solid #00664433;color:#aaffcc;min-width:60px;min-height:24px;flex-shrink:0}
#input-area{padding:16px;border-top:1px solid #00ffcc33;display:flex;gap:10px}
#msg{flex:1;background:#001a11;border:1px solid #00ffcc44;color:#00ffcc;padding:10px 14px;border-radius:8px;font-family:inherit;font-size:1em;resize:none;outline:none}
#msg:focus{border-color:#00ffcc99}
button{background:#006644;color:#00ffcc;border:1px solid #00ffcc44;padding:10px 20px;border-radius:8px;cursor:pointer;font-family:inherit;font-size:.9em}
button:hover{background:#008855}
button:disabled{opacity:.4;cursor:not-allowed}
#compress-btn{background:#0a1a2a;border-color:#4488ff33;color:#88bbff}
#clear-btn{background:#1a0a0a;border-color:#ff444433;color:#ff6666}
.react-block{margin:4px 0;padding:4px 8px;border-radius:4px;font-family:monospace;font-size:0.83em;}
.react-fn{background:#1a2a3a;border-left:3px solid #4a9eff;}
.react-args{background:#1a2a1a;border-left:3px solid #4caf50;}
.react-result{background:#2a1a1a;border-left:3px solid #ff7043;}
.react-label{font-size:0.75em;opacity:0.65;display:block;margin-bottom:2px;}
.react-out{margin:0;white-space:pre-wrap;word-break:break-word;}
.msg-time{display:block;font-size:0.68em;opacity:0.4;margin-top:4px;text-align:right;font-family:monospace;}
.user .msg-time{text-align:right;}
.assistant .msg-time{text-align:left;}
#meta-bar{font-size:0.72em;opacity:0.55;margin-top:3px;font-family:monospace;letter-spacing:0.02em;}
#meta-bar span{margin-right:14px;}
</style></head><body>
<div id="header">
<div><h1>&#9646; KDEV</h1><p>AI coding assistant &mdash; web interface</p><div id="meta-bar"><span id="mb-session">session: —</span><span id="mb-skills">skills: —</span></div></div>
<form method="POST" action="/logout" style="margin:0">
<button style="background:none;border:1px solid #ff444433;color:#ff6666;padding:6px 14px;border-radius:6px;cursor:pointer;font-family:inherit;font-size:.8em" type="submit">Logout</button>
</form></div>
<div id="chat"></div>
<div id="input-area">
<textarea id="msg" rows="1" placeholder="Ask anything..."></textarea>
<button id="send-btn" onclick="sendMsg()">Send</button>
<button id="compress-btn" onclick="compressSession()">Compress</button>
<button id="clear-btn" onclick="clearChat()">Clear</button>
</div>
<script>
const chat=document.getElementById('chat');
const msgEl=document.getElementById('msg');
const sendBtn=document.getElementById('send-btn');
msgEl.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMsg();}});
function addBubble(text,cls){
  const b=document.createElement('div');
  b.className='bubble '+cls;
  b.textContent=text;
  const ts=document.createElement('span');
  ts.className='msg-time';
  const now=new Date();
  ts.textContent=now.getHours().toString().padStart(2,'0')+':'+now.getMinutes().toString().padStart(2,'0')+':'+now.getSeconds().toString().padStart(2,'0');
  b.appendChild(ts);
  chat.appendChild(b);
  chat.scrollTop=chat.scrollHeight;
  return b;
}
const SESSION_ID=(()=>{
  const id='xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{
    const r=Math.random()*16|0;
    return(c==='x'?r:(r&0x3|0x8)).toString(16);
  });
  console.log('[kdev] session_id='+id);
  return id;
})();
fetch('/api/meta').then(r=>r.json()).then(d=>{
  const s=document.getElementById('mb-session');
  const k=document.getElementById('mb-skills');
  if(s)s.textContent='session: '+d.session_prefix;
  if(k)k.textContent='skills: '+d.skills_count;
}).catch(()=>{});
function formatReactBlocks(raw){
  var FUNC='✿FUNCTION✿:';
  var ARGS='✿ARGS✿:';
  var RES='✿RESULT✿:';
  var out='';
  var rem=raw;
  function esc(t){return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
  while(rem.length>0){
    var fi=rem.indexOf(FUNC);
    if(fi===-1){out+=esc(rem);break;}
    if(fi>0){out+=esc(rem.slice(0,fi));}
    var afterFn=rem.slice(fi+FUNC.length);
    var ai=afterFn.indexOf(ARGS);
    var ri=afterFn.indexOf(RES);
    var fi2=afterFn.indexOf(FUNC);
    var fnEnd=afterFn.length;
    if(ai!==-1&&ai<fnEnd)fnEnd=ai;
    if(ri!==-1&&ri<fnEnd)fnEnd=ri;
    if(fi2!==-1&&fi2<fnEnd)fnEnd=fi2;
    var fnName=afterFn.slice(0,fnEnd).trim();
    out+='<div class="react-block react-fn"><span class="react-label">fn: '+esc(fnName)+'</span></div>';
    rem=afterFn.slice(fnEnd);
    if(rem.indexOf(ARGS)===0){
      var afterArgs=rem.slice(ARGS.length);
      var ri2=afterArgs.indexOf(RES);
      var fi3=afterArgs.indexOf(FUNC);
      var argsEnd=afterArgs.length;
      if(ri2!==-1&&ri2<argsEnd)argsEnd=ri2;
      if(fi3!==-1&&fi3<argsEnd)argsEnd=fi3;
      var argsVal=afterArgs.slice(0,argsEnd).trim();
      out+='<div class="react-block react-args"><span class="react-label">args</span><pre class="react-out">'+esc(argsVal)+'</pre></div>';
      rem=afterArgs.slice(argsEnd);
    }
    if(rem.indexOf(RES)===0){
      var afterRes=rem.slice(RES.length);
      var fi4=afterRes.indexOf(FUNC);
      var resEnd=fi4!==-1?fi4:afterRes.length;
      var resVal=afterRes.slice(0,resEnd).trim();
      out+='<div class="react-block react-result"><span class="react-label">result</span><pre class="react-out">'+esc(resVal)+'</pre></div>';
      rem=afterRes.slice(resEnd);
    }
  }
  return out;
}
async function sendMsg(){
  const text=msgEl.value.trim();
  if(!text)return;
  msgEl.value='';
  sendBtn.disabled=true;
  addBubble(text,'user');
  const bubble=addBubble('','assistant');
  try{
    const resp=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,session_id:SESSION_ID})});
    const reader=resp.body.getReader();
    const decoder=new TextDecoder();
    let buf='',done=false,rawBuf='';
    while(!done){
      const{done:d,value}=await reader.read();
      if(d)break;
      buf+=decoder.decode(value,{stream:true});
      const lines=buf.split(String.fromCharCode(10));
      buf=lines.pop();
      for(const line of lines){
        if(line.startsWith('data: ')){
          const data=line.slice(6).trim();
          if(data==='[DONE]'){done=true;break;}
          try{
            const obj=JSON.parse(data);
            if(typeof obj.token==='string'){rawBuf+=obj.token;bubble.textContent+=obj.token;chat.scrollTop=chat.scrollHeight;}
          }catch(e){console.error("SSE parse error on:",data,"err:",e.message);}
        }
      }
    }
    reader.cancel();
    if(rawBuf.indexOf('✿')!==-1){bubble.innerHTML=formatReactBlocks(rawBuf);}
  }catch(e){bubble.textContent='Error: '+e.message;}
  sendBtn.disabled=false;
  msgEl.focus();
}
async function clearChat(){
  await fetch('/clear',{method:'POST'});
  chat.innerHTML='';
}
async function compressSession(){
  const btn=document.getElementById('compress-btn');
  btn.disabled=true;
  btn.textContent='Compressing...';
  const bubble=addBubble('','assistant');
  try{
    const resp=await fetch('/compress',{method:'POST'});
    const data=await resp.json();
    bubble.textContent=data.summary||'Compression failed.';
  }catch(e){
    bubble.textContent='Error: '+e.message;
  }
  btn.disabled=false;
  btn.textContent='Compress';
  chat.scrollTop=chat.scrollHeight;
}
</script></body></html>"""


# ── Web skill saver (Ollama-native, no pydantic-ai) ──────────────────────────
async def web_save_skill(user_task: str, full_response: str) -> None:
    """
    After a complex web UI task, distill it into a skill doc via Ollama.
    Saves to ~/.kdev/skills/ — same pool as terminal REPL.
    Runs as a background task, never blocks the response stream.
    """
    import re as _re
    from datetime import datetime

    model = get_model()
    prompt = f"""You are documenting a reusable skill for a coding agent.

A user asked: "{user_task[:200]}"

The agent's full response was:
{full_response[:1500]}

Write a concise SKILL.md document capturing:
1. When to apply this skill (trigger conditions)
2. The optimal approach / mental model
3. Key commands or tools and their order
4. Pitfalls to avoid

Format EXACTLY as:
---
title: <skill name, max 8 words>
tags: <3-5 keywords, comma separated>
complexity: <simple|medium|complex>
summary: <one line>
---

## When to use
...

## Approach
...

## Tool strategy
...

## Pitfalls
...

Be terse. This will be injected into a system prompt."""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You write precise minimal technical documentation. No padding."},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False
                }
            )
            resp.raise_for_status()
            skill_text = resp.json()["message"]["content"]

        if not skill_text or len(skill_text) < 50:
            return

        slug = _re.sub(r"[^a-z0-9]+", "-", user_task[:50].lower()).strip("-")
        # Overwrite if a skill with same slug already exists (no duplicates)
        existing = list(SKILLS_DIR.glob(f"*-{slug}.md"))
        if existing:
            skill_path = existing[0]
        else:
            ts = datetime.now().strftime("%Y%m%d-%H%M")
            skill_path = SKILLS_DIR / f"{ts}-{slug}.md"
        skill_path.write_text(skill_text, encoding="utf-8")
    except Exception:
        pass  # Never crash the web server over skill saving


# ── Web session compressor (/compress command) ────────────────────────────────
async def web_compress_session(history: list) -> str:
    """
    Distill the current chat_history into a compressed snapshot via Ollama.
    Saves to ~/.kdev/compressed/. Returns the summary text to display in UI.
    """
    import re as _re
    from datetime import datetime
    from pathlib import Path

    if not history:
        return "Nothing to compress — chat history is empty."

    # Build transcript from plain dicts
    lines = []
    for msg in history:
        role = msg.get("role", "")
        content = msg.get("content", "")[:400]
        if role == "user":
            lines.append(f"USER: {content}")
        elif role == "assistant":
            lines.append(f"ASSISTANT: {content}")

    transcript = "\n\n".join(lines)
    if len(transcript) > 6000:
        transcript = transcript[:3000] + "\n\n[...middle trimmed...]\n\n" + transcript[-3000:]

    prompt = f"""Apply knowledge distillation to compress this coding session.

TRANSCRIPT:
{transcript}

Produce a compressed session document with these exact sections:

## Session Summary
2-3 sentences. What was accomplished?

## Key Decisions
Bullet list. Important technical choices made.

## What Worked
Bullet list. Approaches and patterns that were effective.

## What to Remember
Bullet list. Facts to remember in future sessions.

## Memory Update
Max 5 sentences. Permanent reference notes for .agent.md.

## Skills Crystallised
Reusable skills discovered this session. Format: `skill_name: description`

Be ruthlessly concise. Every word must earn its place."""

    model = get_model()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a technical knowledge distillation system. Extract maximum signal, discard all noise."},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False
                }
            )
            resp.raise_for_status()
            result = resp.json()["message"]["content"]
    except Exception as e:
        return f"Compression failed: {e}"

    if not result or len(result) < 50:
        return "Compression failed — model returned empty response."

    # Save snapshot
    from pathlib import Path as _Path
    snap_dir = _Path.home() / ".kdev" / "compressed"
    snap_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    snap_path = snap_dir / f"{ts}-web-session.md"
    snap_path.write_text(
        f"# Compressed Session — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"Source: web UI\n\n" + result,
        encoding="utf-8"
    )

    return result + f"\n\n---\n*Snapshot saved to: {snap_path}*"

@app.get("/", response_class=HTMLResponse)
async def index(kdev_session: str | None = Cookie(default=None)):
    h = {"Cache-Control": "no-store"}
    if not check_auth(kdev_session):
        return HTMLResponse(LOGIN_HTML.replace("{error}", ""), headers=h)
    return HTMLResponse(CHAT_HTML, headers=h)

@app.post("/login")
async def login(request: Request):
    form = await request.form()
    if hashlib.sha256(form.get("password", "").encode()).hexdigest() == get_password_hash():
        token = make_token()
        valid_sessions.add(token)
        resp = Response(status_code=302, headers={"Location": "/"})
        resp.set_cookie(COOKIE_NAME, token, max_age=COOKIE_TTL, httponly=True)
        return resp
    return HTMLResponse(
        LOGIN_HTML.replace("{error}", '<p class="error">Wrong password</p>'),
        headers={"Cache-Control": "no-store"}
    )

@app.post("/logout")
async def logout(kdev_session: str | None = Cookie(default=None)):
    valid_sessions.discard(kdev_session)
    resp = Response(status_code=302, headers={"Location": "/"})
    resp.delete_cookie(COOKIE_NAME)
    return resp

class ChatRequest(BaseModel):
    message: str
    session_id: str = ""

SEARXNG_URL = "http://localhost:4000/search"

def web_search(query: str, num_results: int = 5) -> str:
    """Hit local SearXNG instance and return formatted results string."""
    try:
        resp = requests.get(
            SEARXNG_URL,
            params={"q": query, "format": "json", "categories": "general"},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])[:num_results]
        if not results:
            return "[WEB SEARCH] No results returned."
        lines = [f"[WEB SEARCH] Query: {query}\n"]
        for i, r in enumerate(results, 1):
            title   = r.get("title", "No title")
            url     = r.get("url", "")
            snippet = r.get("content", "No snippet")[:300]
            lines.append(f"{i}. {title}\n   URL: {url}\n   {snippet}\n")
        return "\n".join(lines)
    except Exception as e:
        return f"[WEB SEARCH ERROR] {e}"

from kdev_tools import build_tools_system_prompt, TOOL_REGISTRY as KDEV_TOOL_REGISTRY
TOOLS_SCHEMA = build_tools_system_prompt()
SYSTEM_PROMPT = SYSTEM_PROMPT + TOOLS_SCHEMA


# ── Credential redaction ─────────────────────────────────────────────────────
import re as _re
_REDACT_PATTERNS = [
    _re.compile(r'sk-[A-Za-z0-9]{20,}'),
    _re.compile(r'Bearer [A-Za-z0-9\-._~+/]{20,}'),
    _re.compile(r'(?m)^[A-Z_]*(PASSWORD|API_KEY|SECRET|TOKEN)[A-Z_]*=.+$'),
    _re.compile(r'(?:[A-Za-z0-9+/]{40,}={0,2})(?![A-Za-z0-9+/=])'),
    # T3-H: catch KEY=value inside JSON strings (grep_files output, etc.)
    # Matches PASSWORD/API_KEY/SECRET/TOKEN = anything up to quote/comma/newline
    _re.compile(r'[A-Z_]*(PASSWORD|API_KEY|SECRET|TOKEN)[A-Z_]*=[^\s\'"\\,}]{1,}'),
]

def redact_output(text: str) -> str:
    """Replace credential-like patterns with [REDACTED]."""
    for pat in _REDACT_PATTERNS:
        text = pat.sub('[REDACTED]', text)
    return text


def dispatch_fncall(fn_name: str, args_str: str, session_id: str = 'default') -> str:
    """Dispatch a ✿FUNCTION✿ call to the KDEV tool registry."""
    if fn_name not in KDEV_TOOL_REGISTRY:
        return json.dumps({'returncode': -1, 'output': f'Unknown tool: {fn_name}. Available: {list(KDEV_TOOL_REGISTRY.keys())}'})
    try:
        result = KDEV_TOOL_REGISTRY[fn_name]().call(args_str, session_id=session_id)
        result = redact_output(str(result))
        return result
    except Exception as e:
        return json.dumps({'returncode': -1, 'output': f'Tool dispatch error: {e}'})


def prune_history(messages: list, max_chars: int = 80000) -> list:
    """Drop old tool results when history exceeds max_chars.
    Always keeps the most recent 5 tool results and all user/assistant turns.
    The global chat_history is never modified -- only the copy sent to the LLM.
    """
    total = sum(len(str(m.get("content", ""))) for m in messages)
    if total <= max_chars:
        return messages
    tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    keep_last = 5
    drop_set = set(tool_indices[:max(0, len(tool_indices) - keep_last)])
    pruned = [m for i, m in enumerate(messages) if i not in drop_set]
    dropped_chars = total - sum(len(str(m.get("content", ""))) for m in pruned)
    print(f"[prune] history {total} chars -> {total - dropped_chars} chars"
          f" (dropped {len(drop_set)} tool results)")
    return pruned

@app.get("/api/meta")
async def api_meta():
    import os, glob, uuid
    skills_dir = os.path.expanduser("~/.kdev/skills/")
    try:
        count = len(glob.glob(os.path.join(skills_dir, "*.md")))
    except Exception:
        count = -1
    session_prefix = str(uuid.uuid4())[:8]
    return {"session_prefix": session_prefix, "skills_count": count}


@app.post("/chat")
async def chat_endpoint(req: ChatRequest, kdev_session: str | None = Cookie(default=None)):
    if not check_auth(kdev_session):
        return Response("Unauthorized", status_code=401)

    global chat_history
    session_id = req.session_id if req.session_id else str(uuid.uuid4())
    agent_run_id = str(uuid.uuid4())
    # /map shortcut: build and return repomap directly, skip LLM
    if req.message.strip().startswith("/map"):
        parts = req.message.strip().split(None, 1)
        map_path = parts[1].strip() if len(parts) > 1 else "/home/yanflare/kdev-deploy"
        repomap = build_repomap(map_path)
        if repomap:
            response_text = f"## Repo map: {map_path}\n\n```\n{repomap}\n```"
        else:
            response_text = f"No Python files found in {map_path}"
        chat_history.append({"role": "user", "content": req.message})
        chat_history.append({"role": "assistant", "content": response_text})
        async def map_stream():
            import json
            yield f"data: {json.dumps({'token': response_text})}\n\n"
            yield "data: [DONE]\n\n"
        from starlette.responses import StreamingResponse as _SR
        return _SR(map_stream(), media_type="text/event-stream")
    if req.message.strip().lower().startswith('/events'):
        import json as _ejson
        import os as _eos
        import datetime as _edt
        _eparts = req.message.strip().split(None, 1)
        try:
            _en = int(_eparts[1].strip()) if len(_eparts) > 1 else 20
        except (ValueError, IndexError):
            _en = 20
        _en = max(1, min(_en, 200))
        _epath = _eos.path.expanduser('~/.kdev/events.jsonl')
        _erows = []
        try:
            with open(_epath, 'r', encoding='utf-8') as _ef:
                for _eline in _ef:
                    _eline = _eline.strip()
                    if _eline:
                        try:
                            _erows.append(_ejson.loads(_eline))
                        except Exception:
                            pass
        except FileNotFoundError:
            _erows = []
        _erows = _erows[-_en:]
        _eout = []
        if not _erows:
            _eout.append('No events logged yet.')
        else:
            _eout.append('## Last ' + str(len(_erows)) + ' agent runs')
            _eout.append('')
            _eout.append('| # | Time | Session | Run ID | Hops | Tools | Slowest tool |')
            _eout.append('|---|------|---------|--------|------|-------|--------------|')
            for _ei, _ev in enumerate(_erows, 1):
                _ets = _ev.get('ts', 0)
                _edt_str = _edt.datetime.fromtimestamp(_ets).strftime('%m-%d %H:%M:%S') if _ets else '?'
                _esid = _ev.get('session_id', '?')[:8]
                _erid = _ev.get('agent_run_id', '?')[:8]
                _ehops = str(_ev.get('hops', '?'))
                _etool_calls = str(_ev.get('tool_calls', '?'))
                _etimings = _ev.get('tool_timings', [])
                if _etimings:
                    _eslowest = max(_etimings, key=lambda x: x.get('duration_ms', 0))
                    _eslow_str = _eslowest.get('tool', '?') + ' ' + str(_eslowest.get('duration_ms', '?')) + 'ms'
                else:
                    _eslow_str = '-'
                _eout.append('| ' + str(_ei) + ' | ' + _edt_str + ' | ' + _esid + ' | ' + _erid + ' | ' + _ehops + ' | ' + _etool_calls + ' | ' + _eslow_str + ' |')
        _eresponse = chr(10).join(_eout)
        chat_history.append({'role': 'user', 'content': req.message})
        chat_history.append({'role': 'assistant', 'content': _eresponse})
        async def _events_stream():
            yield 'data: ' + _ejson.dumps({'token': _eresponse}) + chr(10) + chr(10)
            yield 'data: [DONE]' + chr(10) + chr(10)
        from starlette.responses import StreamingResponse as _ESR
        return _ESR(_events_stream(), media_type='text/event-stream')

    if req.message.strip().lower().startswith('/evolve-log'):
        import os as _elos
        import json as _eljson
        _elparts = req.message.strip().split(None, 1)
        try:
            _eln = int(_elparts[1].strip()) if len(_elparts) > 1 else 60
        except (ValueError, IndexError):
            _eln = 60
        _eln = max(1, min(_eln, 500))
        _elpath = _elos.path.expanduser('~/.kdev/evolve-log.md')
        try:
            with open(_elpath, 'r', encoding='utf-8') as _elf:
                _ellines = _elf.readlines()
            _ellines = _ellines[-_eln:]
            _eltext = '## evolve-log (last ' + str(len(_ellines)) + ' lines)' + chr(10) + chr(10) + '```' + chr(10) + ''.join(_ellines).rstrip() + chr(10) + '```'
        except FileNotFoundError:
            _eltext = 'evolve-log.md not found at ' + _elpath
        except Exception as _ele:
            _eltext = 'Error reading evolve-log: ' + str(_ele)
        chat_history.append({'role': 'user', 'content': req.message})
        chat_history.append({'role': 'assistant', 'content': _eltext})
        async def _evolve_log_stream():
            yield 'data: ' + _eljson.dumps({'token': _eltext}) + chr(10) + chr(10)
            yield 'data: [DONE]' + chr(10) + chr(10)
        from starlette.responses import StreamingResponse as _ELSR
        return _ELSR(_evolve_log_stream(), media_type='text/event-stream')


    if req.message.strip().lower().startswith("/web-search"):
        query = req.message.strip()[len("/web-search"):].strip()
        if not query:
            async def _empty():
                yield "data: " + __import__("json").dumps({"token": "Usage: /web-search <your query>"}) + "\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(_empty(), media_type="text/event-stream")
        search_results = web_search(query)
        augmented = search_results + "\n\nBased on the above web search results, answer: " + query
        chat_history.append({"role": "user", "content": augmented})
    else:
        chat_history.append({"role": "user", "content": req.message})
    # T1-D: update last_activity on every web UI message (inactivity autopilot signal)
    try:
        import time as _t
        open('/home/yanflare/.kdev/last_activity', 'w').write(str(int(_t.time())))
    except Exception:
        pass
    model = get_model()

    # Messages sent to Ollama: system prompt prepended, but NOT stored in chat_history
    def build_messages():
        system = SYSTEM_PROMPT
        if SKILLS_AVAILABLE:
            injected = load_relevant_skills(req.message, max_skills=3)
            if injected:
                system = SYSTEM_PROMPT.rstrip() + "\n\n" + injected
        if MEMORY_AVAILABLE:
            mem_context = query_memory(req.message, max_memories=5)
            if mem_context:
                system = system.rstrip() + "\n\n" + mem_context
        # /map trigger: inject repomap into system prompt
        if req.message.strip().startswith("/map"):
            parts = req.message.strip().split(None, 1)
            map_path = parts[1].strip() if len(parts) > 1 else "/home/yanflare/kdev-deploy"
            repomap = build_repomap(map_path)
            if repomap:
                map_block = f"## Repo map: {map_path}\n\n```\n{repomap}\n```"
                system = system.rstrip() + "\n\n" + map_block
        history_for_llm = prune_history(chat_history)
        return [{"role": "system", "content": system}] + history_for_llm

    async def stream():
        global chat_history
        full = ""
        _ft_trace = []
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    "http://localhost:11434/api/chat",
                    json={"model": model, "messages": build_messages(), "stream": True}
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            token = obj.get("message", {}).get("content", "")
                            if token:
                                full += token
                                yield f"data: {json.dumps({'token': token})}\n\n"
                            if obj.get("done"):
                                break
                        except Exception:
                            continue
        except Exception as e:
            yield f"data: {json.dumps({'token': f'Error: {e}'})}\n\n"
            chat_history.append({"role": "assistant", "content": full})
            yield "data: [DONE]\n\n"
            return

        chat_history.append({"role": "assistant", "content": full})
        _ft_trace.append({"role": "assistant", "content": full})

        # ── Exec loop (max MAX_EXEC_HOPS hops) ───────────────────────────────
        iteration_count = 0
        _tool_timings = []
        for hop in range(MAX_EXEC_HOPS):
            iteration_count += 1
            # ── fncall parser (primary) — ✿FUNCTION✿ format ─────────────
            fn_match = FNCALL_PATTERN.search(full)
            if fn_match:
                fn_name = fn_match.group(1)
                args_str = fn_match.group(2)
                import time as _ttime
                _t0 = _ttime.perf_counter()
                exec_result = dispatch_fncall(fn_name, args_str, session_id=session_id)
                _t1 = _ttime.perf_counter()
                _dur_ms = round((_t1 - _t0) * 1000)
                _tier = TOOL_TIER.get(fn_name, 'unknown')
                print('[tool] ' + fn_name + ' [' + _tier + '] ' + str(_dur_ms) + 'ms args=' + args_str[:120], flush=True)
                _tool_timings.append({'tool': fn_name, 'tier': _tier, 'duration_ms': _dur_ms})
                _safe_exec_result = str(exec_result).replace('\u273fFUNCTION\u273f', '[FUNCTION]').replace('\u273fARGS\u273f', '[ARGS]').replace('\u273fRESULT\u273f', '[RESULT]')
                observation = "[iteration " + str(iteration_count) + "/30]\n✿RESULT✿: " + _safe_exec_result
            else:
                break
            yield f"data: {json.dumps({'token': f'\n\n{observation}\n\n'})}\n\n"
            # Feed result back as a user message and get next reply
            _ft_trace.append({"role": "user", "content": observation})
            chat_history.append({"role": "user", "content": observation})
            try:
                full = await ollama_complete(build_messages(), model)
            except Exception as e:
                full = f"Error during exec follow-up: {e}"
            _ft_trace.append({"role": "assistant", "content": full})
            chat_history.append({"role": "assistant", "content": full})
            # Stream the follow-up reply token by token (send as one chunk)
            yield f"data: {json.dumps({'token': full})}\n\n"

        # ── Skill save (background, non-blocking) ────────────────────────────
        if SKILLS_AVAILABLE:
            ran_exec = any(t['tool'] != 'tool_list' for t in _tool_timings)
            is_complex = ran_exec
            if is_complex:
                try:
                    loop = asyncio.get_event_loop()
                    loop.create_task(web_save_skill(req.message, full))
                except Exception as e:
                    print(f"[skill-save] create_task failed: {e}", flush=True)

        if MEMORY_AVAILABLE:
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(ingest_memory(req.message, full, session_id=session_id, agent_run_id=agent_run_id))
            except Exception as e:
                print(f"[memory] ingest create_task failed: {e}", flush=True)

        # -- JSONL event log --------------------------------------------------
        try:
            import time as _time
            _event = json.dumps({
                'ts': _time.time(),
                'session_id': session_id,
                'agent_run_id': agent_run_id,
                'tool_calls': iteration_count,
                'hops': hop + 1,
                'tool_timings': _tool_timings,
                'message': req.message[:120],
            })
            _elog = Path('/home/yanflare/.kdev/events.jsonl')
            with open(_elog, 'a', encoding='utf-8') as _ef:
                _ef.write(_event + '\n')
        except Exception as _elog_err:
            print('[event-log] failed: ' + str(_elog_err), flush=True)

        # -- Fine-tune data pipeline --------------------------------------
        try:
            import time as _ftime
            _ft_has_tools = iteration_count > 0
            _ft_long_enough = len(full) > 100
            _ft_no_error = not full.strip().startswith('Error:')
            if _ft_has_tools and _ft_long_enough and _ft_no_error:
                _ft_record = json.dumps({
                    'messages': [
                        {'role': 'user', 'content': req.message},
                        {'role': 'assistant', 'content': full},
                    ],
                    'ts': _ftime.time(),
                    'agent_run_id': agent_run_id,
                })
                _ftlog = Path('/home/yanflare/.kdev/finetune.jsonl')
                with open(_ftlog, 'a', encoding='utf-8') as _ftf:
                    _ftf.write(_ft_record + '\n')
                print('[finetune] record saved (' + str(len(full)) + ' chars)', flush=True)
        except Exception as _ft_err:
            print('[finetune] failed: ' + str(_ft_err), flush=True)
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/compress")
async def compress_endpoint(kdev_session: str | None = Cookie(default=None)):
    if not check_auth(kdev_session):
        return Response("Unauthorized", status_code=401)
    result = await web_compress_session(chat_history)
    if MEMORY_AVAILABLE:
        try:
            await run_consolidation()
        except Exception as e:
            print(f"[memory] compress consolidation failed: {e}", flush=True)
    return JSONResponse({"summary": result})

@app.post("/clear")
async def clear(kdev_session: str | None = Cookie(default=None)):
    if not check_auth(kdev_session):
        return Response("Unauthorized", status_code=401)
    global chat_history
    chat_history = []
    return {"ok": True}

class ExecRequest(BaseModel):
    command: str
    timeout: int = 30

@app.post("/exec")
async def exec_endpoint(req: ExecRequest, kdev_session: str | None = Cookie(default=None)):
    if not check_auth(kdev_session):
        return Response("Unauthorized", status_code=401)
    output = run_shell(req.command, timeout=req.timeout)
    return JSONResponse({"output": output})


@app.on_event("startup")
async def startup_event():
    if MEMORY_AVAILABLE:
        loop = asyncio.get_event_loop()
        loop.create_task(consolidation_loop())
        print("[memory] consolidation loop started", flush=True)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
