#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# kdev install script for Linux
# Run from the directory containing this file:  bash install.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
RESET='\033[0m'

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$HOME/.kdev-venv"
KDEV_DATA="$HOME/.kdev"

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║        kdev installer — Linux        ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════╝${RESET}"
echo ""

# ── 1. Check Python version ───────────────────────────────────────────────────
echo -e "${BOLD}[1/6] Checking Python version...${RESET}"
PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON" ]; then
    echo -e "${RED}ERROR: python3 not found. Install it first:${RESET}"
    echo "  sudo apt update && sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

PYVER=$($PYTHON --version 2>&1 | grep -oP '\d+\.\d+')
PYMAJ=$(echo "$PYVER" | cut -d. -f1)
PYMIN=$(echo "$PYVER" | cut -d. -f2)

if [ "$PYMAJ" -lt 3 ] || ([ "$PYMAJ" -eq 3 ] && [ "$PYMIN" -lt 11 ]); then
    echo -e "${YELLOW}WARNING: Python $PYVER detected. kdev requires 3.11+.${RESET}"
    echo "  Install newer Python via deadsnakes PPA:"
    echo "    sudo add-apt-repository ppa:deadsnakes/ppa"
    echo "    sudo apt install python3.11 python3.11-venv"
    echo ""
    echo -e "${YELLOW}Continuing anyway — may fail on older Python.${RESET}"
else
    echo -e "  ${GREEN}✓${RESET} Python $PYVER — OK"
fi

# ── 2. Create virtual environment ─────────────────────────────────────────────
echo ""
echo -e "${BOLD}[2/6] Creating virtual environment at ${VENV_PATH}...${RESET}"
if [ -d "$VENV_PATH" ]; then
    echo -e "  ${YELLOW}⚠${RESET}  venv already exists — skipping creation (delete $VENV_PATH to recreate)"
else
    $PYTHON -m venv "$VENV_PATH"
    echo -e "  ${GREEN}✓${RESET} Created $VENV_PATH"
fi

# ── 3. Install requirements ───────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[3/6] Installing Python dependencies...${RESET}"
"$VENV_PATH/bin/pip" install --quiet --upgrade pip
"$VENV_PATH/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"
echo -e "  ${GREEN}✓${RESET} All packages installed"

# ── 4. Create ~/.kdev/ directory structure ────────────────────────────────────
echo ""
echo -e "${BOLD}[4/6] Creating ~/.kdev/ data directories...${RESET}"
mkdir -p "$KDEV_DATA/sessions"
mkdir -p "$KDEV_DATA/skills"
mkdir -p "$KDEV_DATA/compressed"
echo -e "  ${GREEN}✓${RESET} $KDEV_DATA/{sessions,skills,compressed}"

# Copy bundled skills (learned from previous sessions)
SKILLS_SRC="$INSTALL_DIR/kdev-skills"
if [ -d "$SKILLS_SRC" ] && [ "$(ls -A "$SKILLS_SRC")" ]; then
    SKILL_COUNT=$(ls "$SKILLS_SRC" | wc -l)
    cp -n "$SKILLS_SRC"/*.md "$KDEV_DATA/skills/" 2>/dev/null || true
    echo -e "  ${GREEN}✓${RESET} Restored $SKILL_COUNT skill(s) to $KDEV_DATA/skills/"
fi

# Copy agent memory files
MEMORY_SRC="$INSTALL_DIR/agent-memory"
if [ -f "$MEMORY_SRC/user-agent.md" ]; then
    cp "$MEMORY_SRC/user-agent.md" "$KDEV_DATA/agent.md"
    echo -e "  ${GREEN}✓${RESET} Restored user memory → $KDEV_DATA/agent.md"
fi
if [ -f "$MEMORY_SRC/workspace-agent.md" ]; then
    cp "$MEMORY_SRC/workspace-agent.md" "$INSTALL_DIR/.agent.md"
    echo -e "  ${GREEN}✓${RESET} Restored workspace memory → $INSTALL_DIR/.agent.md"
fi

# ── 5. Set up .env ────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[5/6] Setting up .env config...${RESET}"
ENV_FILE="$INSTALL_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    echo -e "  ${YELLOW}⚠${RESET}  .env already exists — not overwriting"
    echo -e "       Edit it manually: ${CYAN}nano $ENV_FILE${RESET}"
else
    cp "$INSTALL_DIR/.env.template" "$ENV_FILE"
    echo -e "  ${GREEN}✓${RESET} Created .env from template"
    echo -e "  ${YELLOW}➜  IMPORTANT: Edit .env now:${RESET} ${CYAN}nano $ENV_FILE${RESET}"
    echo -e "       Set OLLAMA_BASE_URL and OLLAMA_MODEL at minimum."
fi

# ── 6. Create kdev alias in ~/.bashrc ─────────────────────────────────────────
echo ""
echo -e "${BOLD}[6/6] Installing 'kdev' alias...${RESET}"
ALIAS_LINE="alias kdev='$VENV_PATH/bin/python $INSTALL_DIR/kdev.py'"
ALIAS_COMMENT="# kdev — private coding agent"

if grep -q "alias kdev=" "$HOME/.bashrc" 2>/dev/null; then
    echo -e "  ${YELLOW}⚠${RESET}  'kdev' alias already in ~/.bashrc — not overwriting"
    echo -e "       Update it manually if the path has changed."
else
    echo "" >> "$HOME/.bashrc"
    echo "$ALIAS_COMMENT" >> "$HOME/.bashrc"
    echo "$ALIAS_LINE" >> "$HOME/.bashrc"
    echo -e "  ${GREEN}✓${RESET} Added to ~/.bashrc"
fi

# Also add to ~/.bash_profile if it exists and sources .bashrc
if [ -f "$HOME/.bash_profile" ] && ! grep -q "alias kdev=" "$HOME/.bash_profile" 2>/dev/null; then
    echo "" >> "$HOME/.bash_profile"
    echo "$ALIAS_COMMENT" >> "$HOME/.bash_profile"
    echo "$ALIAS_LINE" >> "$HOME/.bash_profile"
    echo -e "  ${GREEN}✓${RESET} Also added to ~/.bash_profile"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║                 Install complete! ✓                  ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "${BOLD}Next steps:${RESET}"
echo ""
echo -e "  ${CYAN}1. Edit your .env:${RESET}"
echo -e "     nano $ENV_FILE"
echo -e "     (Set OLLAMA_BASE_URL=http://localhost:11434 and OLLAMA_MODEL=qwen3:27b)"
echo ""
echo -e "  ${CYAN}2. Verify Ollama is running:${RESET}"
echo -e "     curl http://localhost:11434/api/tags"
echo -e "     ollama list   # confirm qwen3:27b is present"
echo ""
echo -e "  ${CYAN}3. Reload your shell:${RESET}"
echo -e "     source ~/.bashrc"
echo ""
echo -e "  ${CYAN}4. Launch kdev:${RESET}"
echo -e "     kdev                          # interactive REPL"
echo -e "     kdev \"hello, are you running?\" # single-shot test"
echo ""
echo -e "  ${CYAN}5. Read the boot briefing:${RESET}"
echo -e "     cat $INSTALL_DIR/LINUX_BOOT_PROMPT.md"
echo ""
echo -e "${YELLOW}Known issue on fresh Linux install:${RESET}"
echo -e "  MCP tools (nautilus.exe) are Windows-only. kdev will print a yellow"
echo -e "  warning and run without file/shell MCP tools. Core chat works fine."
echo -e "  See MIGRATION_CHECKLIST.md §3 for Linux MCP alternatives."
echo ""
