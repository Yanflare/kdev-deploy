## Session Plan

### Task 1: Improve Linux Boot Briefing
Files: /home/yanflare/kdev-deploy/LINUX_BOOT_PROMPT.md
Description: Update LINUX_BOOT_PROMPT.md to include a reminder about the location and usage of the `.env` file for Ollama settings. Add instructions on how to set up an editor command if `nano` is not preferred.

### Task 2: Enhance Workspace Behavior Rules
Files: agent-memory/workspace-agent.md
Description: Update workspace-agent.md with additional notes regarding the degraded functionality of MCP tools due to the absence of nautilus.exe on Linux. Include a note about gracefully handling the lack of these tools without crashing the system.

### Task 3: Simplify User Profile Preferences
Files: agent-memory/user-agent.md
Description: Clarify in user-agent.md that the `/memory` command currently opens files with an editor but does not specify which editor, and that users can set their preferred editor via environment variables.