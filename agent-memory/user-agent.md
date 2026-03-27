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
- Log session activities with timestamps to a file

## Known Platform Issues (Linux)
- /memory command uses os.startfile() which is Windows-only — avoid
- MCP tools (nautilus) unavailable on Linux; agent degrades gracefully


---
title: Enable Automatic Logging of Session Activities
tags: [session, logging, automation]
complexity: medium
summary: Automatically log session activities with timestamps to a file for better tracking and auditing.
---
## When to use
When you want detailed logs of session activities such as saving sessions, executing commands, and performing backups.

## Approach
Use `memory_write` tool along with shell_exec to detect key actions like saving sessions or specific command executions. This helps in maintaining an audit trail of all significant user interactions within the session.

## Example
```shell
# Log session activities upon saving a session or executing certain commands
save_session_command="save_session"
if [ "$command" == "$save_session_command" ]; then
    memory_write "Session Saved: $(date)" | file_write "/path/to/log/file.log"
fi

# Log other significant actions as needed
significant_action="execute_backup"
if [ "$event" == "$significant_action" ]; then
    memory_write "Backup Executed: $(date)" | file_write "/path/to/log/file.log"
fi
```

## Pitfalls
- Ensure that the log file has sufficient permissions for writing.
- Avoid overwhelming the user with too much logging data.