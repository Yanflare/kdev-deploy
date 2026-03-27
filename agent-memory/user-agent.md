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

## Known Platform Issues (Linux)
- /memory command uses os.startfile() which is Windows-only — avoid
- MCP tools (nautilus) unavailable on Linux; agent degrades gracefully

---
title: Enable Automatic Session Summarization
tags: [session, summarization, memory]
complexity: low
summary: Automatically summarize session contents before saving to enhance user experience.
---
## When to use
When auto-saving sessions every hour and you want an automatic summary of the session content before saving.

## Approach
Use `memory_write` tool to write a summary of the session contents just before saving. This helps in enhancing efficiency by providing a concise overview of the session activities, thus improving user experience. Adjust the summary generation logic to include more recent activities if possible.

## Example
```shell
# Summarize the current session and save it with an automatic label indicating the timestamp
session_summary=$(echo "Session Summary: $(date)" && memory_read)
memory_write "$session_summary"
```

## Pitfalls
- Ensure that the summary is concise to avoid overwhelming the user with details.
- Use `date` command to label summaries uniquely for easy reference.