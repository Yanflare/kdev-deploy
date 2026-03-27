===
## About Me
- Running kdev on Linux (migrated from Windows 2026-03-14)
- Primary LLM: Ollama local, model qwen2.5-abliterate:14b-instruct-q4_K_M

## Preferences
- Concise responses; skip preamble
- Read code before editing — no guessing at structure
- Break down complex tasks into smaller steps
- Break tasks into single actions without chaining unprompted
- Avoid complex actions without explicit instructions
- Auto-save sessions every hour to enhance user experience
- Automatically summarize session contents before saving using `memory_write` tool to enhance efficiency and user experience
- Conduct automatic network diagnostics upon session start for improved troubleshooting
- Save sessions automatically when logging out or executing specific commands (e.g., save_session)

## Known Platform Issues (Linux)
- /memory command uses os.startfile() which is Windows-only — avoid
- MCP tools (nautilus) unavailable on Linux; agent degrades gracefully

---
title: Enable Automatic Session Backups Upon Specific Events
tags: [session, backup, automation]
complexity: medium
summary: Automatically save session backups upon logout or specific commands to enhance user experience.
---
## When to use
When you want automatic session backups not only every hour but also when logging out or executing certain commands like `save_session`.

## Approach
Use `memory_write` tool along with event triggers (like shell_exec) to detect logouts and command executions. This helps in creating seamless backup experiences without manual intervention.

## Example
```shell
# Save session automatically upon logout or specific command execution
logout_command="exit"
if [ "$command" == "$logout_command" ] || [ "$event" == "logout" ]; then
    memory_write "Session Backup: $(date)"
fi

# Trigger save_session manually if needed
save_session_command="save_session"
if [ "$command" == "$save_session_command" ]; then
    memory_write "User-initiated Session Save: $(date)"
fi
```

## Pitfalls
- Ensure that the event detection logic is robust and does not interfere with other commands.
- Use appropriate command names as per your environment setup.