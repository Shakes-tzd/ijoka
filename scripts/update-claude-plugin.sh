#!/bin/bash
# update-claude-plugin.sh
# Commits plugin changes to GitHub and reinstalls the Claude Code plugin
#
# Usage: ./scripts/update-claude-plugin.sh [commit message]
#
# If no commit message is provided, a default message is used.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PLUGIN_DIR="$PROJECT_ROOT/packages/claude-plugin"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Ijoka Plugin Update Script ===${NC}"

# Check if we're in the right directory
if [ ! -d "$PLUGIN_DIR" ]; then
    echo -e "${RED}Error: Plugin directory not found at $PLUGIN_DIR${NC}"
    exit 1
fi

cd "$PROJECT_ROOT"

# Check for uncommitted changes in the plugin directory
PLUGIN_CHANGES=$(git status --porcelain packages/claude-plugin/ 2>/dev/null)

if [ -n "$PLUGIN_CHANGES" ]; then
    echo -e "${YELLOW}Found changes in plugin directory:${NC}"
    echo "$PLUGIN_CHANGES"
    echo ""

    # Get commit message
    if [ -n "$1" ]; then
        COMMIT_MSG="$1"
    else
        COMMIT_MSG="chore(plugin): update Claude Code plugin"
    fi

    echo -e "${GREEN}Staging plugin changes...${NC}"
    git add packages/claude-plugin/

    echo -e "${GREEN}Committing changes...${NC}"
    git commit -m "$COMMIT_MSG

Co-Authored-By: Claude <noreply@anthropic.com>"

    echo -e "${GREEN}Pushing to GitHub...${NC}"
    git push
else
    echo -e "${YELLOW}No uncommitted changes in plugin directory${NC}"
fi

# Reinstall the plugin
echo ""
echo -e "${GREEN}Reinstalling Claude Code plugin...${NC}"

# Remove from cache to ensure clean install
CACHE_DIR="$HOME/.claude/plugins/cache/ijoka"
if [ -d "$CACHE_DIR" ]; then
    echo -e "${YELLOW}Removing cached plugin...${NC}"
    rm -rf "$CACHE_DIR"
fi

# Also remove capitalized version if exists
CACHE_DIR_CAP="$HOME/.claude/plugins/cache/Ijoka"
if [ -d "$CACHE_DIR_CAP" ]; then
    echo -e "${YELLOW}Removing cached plugin (capitalized)...${NC}"
    rm -rf "$CACHE_DIR_CAP"
fi

# Install from local directory (this handles uninstall/reinstall automatically)
echo -e "${GREEN}Installing plugin from local directory...${NC}"
cd "$PLUGIN_DIR"
claude /plugin install .

echo ""
echo -e "${GREEN}=== Plugin update complete! ===${NC}"
echo -e "${YELLOW}Note: You may need to restart Claude Code for changes to take effect.${NC}"
