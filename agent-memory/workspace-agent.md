===
title: Enhanced Graceful Degradation for Session Commands
tags: [session-management, linux-support, graceful-degradation]
complexity: medium
summary: This skill describes how to handle session commands in a way that ensures graceful degradation when MCP tools are not available.
## When to use
Use this skill when you need to ensure that session-related commands work smoothly even on systems where MCP tools are unavailable.

## Approach
Check if the necessary MCP tools are present before executing session management commands. If MCP tools are not found, perform basic session cleanup and compression without using these tools.

## Example
To manually trigger session compression after a session, use the following command:
```
/compress
```
When MCP tools are unavailable (e.g., on Linux), this command will degrade gracefully and perform basic session cleanup without compressing the session data. For instance, you can check if the necessary tool is present before executing:

```python
if file_read(os.path.join(MCP_PATH, "tool.exe")):
    # Execute session management commands as usual
else:
    # Perform basic session cleanup
```

## Pitfalls
- Ensure that all paths and tools referenced are checked for existence to avoid failures.
- Users might need to manually perform additional steps if MCP tools are not available.