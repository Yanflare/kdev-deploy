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

# Custom aliases for network diagnostics commands
alias ping_gw="ping -c 4 gateway_ip_address"
alias trace_route="traceroute destination_host_name_or_IP"

# New custom shell aliases based on user preferences
alias mylogs="tail -f /path/to/log/file.log" # For quick access to log files
alias search_files='grep_files -r "search_term" /path/to/search/directory' # Using KDEV tool for searching files
```

title: Enable Quick File Search with Custom Shell Alias
tags: [shell, search, efficiency]
complexity: low
summary: Use custom shell aliases to quickly run file searches using the `grep_files` KDEV tool.
---
## When to use
When you want to quickly search through files for a specific term.

## Approach
Create custom shell alias that maps short commands to frequently used KDEV tools like `grep_files`. This reduces keystrokes and saves time when performing regular checks on file contents.

## Example
```shell
# Alias for quick file searching with grep_files tool.
alias search_files='grep_files -r "search_term" /path/to/search/directory'
```

## Pitfalls
- Ensure that the `search_term` is correctly set in your alias definition.