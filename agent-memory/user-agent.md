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

## Automate Common User Tasks with Cron Jobs
You can automate common tasks using cron jobs, which run scheduled commands at specified intervals. For example, you could schedule daily backups of your project directories or weekly summaries of your log files.

title: Schedule Daily Backups Using Cron Jobs
tags: [cron, automation, efficiency]
complexity: low
summary: Use cron to automatically back up your projects every day.
---
## When to use
When you want to ensure regular backups without manual intervention.

## Approach
Edit the crontab file using `crontab -e` and add a line to schedule daily backups. For example, to create a backup of `/path/to/projects` at 3 AM every day:

```shell
0 3 * * * tar czf /backup/path/project_backup_$(date +%Y%m%d).tar.gz /path/to/projects > /dev/null 2>&1
```

## Example
```shell
# Schedule daily backup of projects directory
crontab -e
# Add the following line and save:
0 3 * * * tar czf /backup/path/project_backup_$(date +%Y%m%d).tar.gz /path/to/projects > /dev/null 2>&1
```

## Pitfalls
- Ensure there is enough disk space for backups.
- Verify the backup path exists before scheduling.

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

# Aliases for cron management
alias crontab_edit="crontab -e"
alias check_cron_jobs="crontab -l | grep -v '^#' | grep -v '^\$'"

# Custom aliases for timezone commands
alias set_timezone='sudo timedatectl set-timezone "Region/City"'
alias show_timezone='timedatectl | grep "Time zone:"'
```

title: Set and Display Timezone Information Using Shell Aliases
tags: [timezone, shell, efficiency]
complexity: low
summary: Use custom shell aliases to easily set and display your system's timezone information.
---
## When to use
When you need quick access to setting or displaying the current timezone on your Linux system.

## Approach
Use `timedatectl` command in combination with shell aliases for setting and showing the timezone. This makes it easy to adjust the timezone without remembering full command syntax each time.

## Example
```shell
# Set a specific timezone, e.g., New York (America/New_York)
set_timezone

# Show current timezone settings
show_timezone
```

## Pitfalls
- Make sure you know the correct region/city name for your desired timezone.