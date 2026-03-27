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
alias documents="cd /path/to/documents"

# Alias for running memory_write to log session activities
alias log_activity="memory_write 'Activity: $(date)' | file_write '/path/to/log/file.log'"

# Example alias for frequently used KDEV tools
alias save_session='save_session_command'
alias backup_now='execute_backup'

# Alias for quick navigation and operations in home directory
alias homedir="cd ~"
alias myfiles="ls -l ~/my_files_directory"
```

## Known Platform Issues (Linux)
- /memory command uses os.startfile() which is Windows-only — avoid
- MCP tools (nautilus) unavailable on Linux; agent degrades gracefully

title: Enable Quick Navigation to Common Directories with Custom Shell Aliases
tags: [shell, navigation, automation]
complexity: low
summary: Use custom shell aliases for quick access to commonly used directories to enhance efficiency.
---
## When to use
When you want to quickly navigate to your most frequently accessed directories without typing long path names.

## Approach
Create custom shell aliases that map short commands to the full paths of your favorite directories. This reduces keystrokes and saves time when switching between projects or document folders.

## Example
```shell
# Navigate directly to project directory with a simple alias command.
alias projects="cd /path/to/projects"
```

## Pitfalls
- Ensure the aliases point to correct paths and update them if your file structure changes.