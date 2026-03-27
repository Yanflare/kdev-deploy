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

## Enhance Efficiency with Custom Shell Aliases
Custom shell aliases can significantly improve your workflow by reducing the need to type long commands repeatedly. Below are some examples of beneficial aliases that enhance efficiency and convenience:

```shell
# Example alias for frequently used commands
alias ll='ls -l'
alias ..='cd ..'

# Alias for quick directory navigation
alias projects="cd /path/to/projects"

# Alias for running memory_write to log session activities
alias log_activity="memory_write 'Activity: $(date)' | file_write '/path/to/log/file.log'"

# Example alias for frequently used KDEV tools
alias save_session='save_session_command'
alias backup_now='execute_backup'
```

## Known Platform Issues (Linux)
- /memory command uses os.startfile() which is Windows-only — avoid
- MCP tools (nautilus) unavailable on Linux; agent degrades gracefully


---
title: Enable Automatic Logging of Session Activities with Custom Shell Aliases
tags: [session, logging, automation]
complexity: medium
summary: Automatically log session activities with timestamps to a file for better tracking and auditing using custom shell aliases.
---
## When to use
When you want detailed logs of session activities such as saving sessions, executing commands, and performing backups.

## Approach
Use `memory_write` tool along with shell_exec to detect key actions like saving sessions or specific command executions. Create custom shell aliases for these actions to log them automatically.

## Example
```shell
# Log session activities upon saving a session or executing certain commands
alias save_session='save_session_command | memory_write "Session Saved: $(date)" | file_write "/path/to/log/file.log"'
```

## Pitfalls
- Ensure that the log file has sufficient permissions for writing.
- Avoid overwhelming the user with too much logging data.