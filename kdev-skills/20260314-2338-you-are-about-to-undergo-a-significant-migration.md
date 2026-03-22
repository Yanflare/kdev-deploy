---
title: Cross-Platform Migration Audit and Handoff Prep
tags: migration, audit, documentation, cross-platform, workspace
complexity: complex
summary: Audit a workspace for platform-specific assumptions and produce self-briefing artifacts before environment migration.
---

## When to use
- Agent or environment is changing OS, shell, model, or toolchain imminently
- Need to preserve project state across a session boundary with no shared memory
- Asked to "prepare for migration" or "leave notes for future self"

## Approach
Two-phase: **audit first, document second.** Don't create docs until you've actually read the code — guessed checklists miss real issues. Treat the future agent as a new colleague with zero context: assume nothing carries over. The deliverables are (1) a technical checklist for what to fix, (2) a human-readable boot briefing, and (3) a session note appended to the persistent agent memory file.

Severity-rank findings: distinguish "will crash" from "graceful degradation" from "irrelevant on new platform."

## Tool strategy
1. `expand_folder` — get full workspace tree before touching anything
2. `open_files` + `expand_code_chunks` — read actual source; don't guess at paths or APIs
3. `powershell`/shell — verify live state (what's installed, what .env contains, git status)
4. `create_file` — write MIGRATION_CHECKLIST.md, LINUX_BOOT_PROMPT.md
5. `find_and_replace_code` — patch .agent.md session note in place
6. Final shell command — confirm all files exist and are non-empty

Read before writing. Create files only after audit is complete.

## Pitfalls
- `os.startfile()` is Windows-only and raises at runtime on Linux — easy to miss in audit if you only search for `.exe`
- Hardcoded absolute paths may appear in multiple files; search all, not just the main entrypoint
- The boot briefing must be self-contained — don't assume the reader has read the checklist
- Don't mark migration "done" without verifying created files are non-empty (shell confirm step)