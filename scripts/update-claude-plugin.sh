#!/bin/bash
# update-claude-plugin.sh
# Commits plugin changes to GitHub and reinstalls the plugin FROM GitHub
#
# Usage: ./scripts/update-claude-plugin.sh [commit message]
#
# If no commit message is provided, a default message is used.
# The plugin is always installed from GitHub (not local) to ensure consistency.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PLUGIN_DIR="$PROJECT_ROOT/packages/claude-plugin"
GITHUB_REPO="Shakes-tzd/ijoka"
MARKETPLACE_NAME="ijoka"

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

# Check for uncommitted changes in the plugin directory OR marketplace config
PLUGIN_CHANGES=$(git status --porcelain packages/claude-plugin/ .claude-plugin/ 2>/dev/null)

if [ -n "$PLUGIN_CHANGES" ]; then
    echo -e "${YELLOW}Found uncommitted changes:${NC}"
    echo "$PLUGIN_CHANGES"
    echo ""

    # Get commit message
    if [ -n "$1" ]; then
        COMMIT_MSG="$1"
    else
        COMMIT_MSG="chore(plugin): update Claude Code plugin"
    fi

    echo -e "${GREEN}Staging changes...${NC}"
    git add packages/claude-plugin/ .claude-plugin/

    echo -e "${GREEN}Committing changes...${NC}"
    git commit -m "$COMMIT_MSG

Co-Authored-By: Claude <noreply@anthropic.com>"

    echo -e "${GREEN}Pushing to GitHub...${NC}"
    git push
else
    echo -e "${YELLOW}No uncommitted changes in plugin directory${NC}"
fi

# Ensure the marketplace is configured
echo ""
echo -e "${GREEN}Checking marketplace configuration...${NC}"

if ! claude plugin marketplace list 2>/dev/null | grep -q "$MARKETPLACE_NAME"; then
    echo -e "${YELLOW}Adding ijoka marketplace from GitHub...${NC}"
    claude plugin marketplace add "$GITHUB_REPO"
fi

# Update marketplace from GitHub
echo -e "${GREEN}Updating marketplace from GitHub...${NC}"
claude plugin marketplace update "$MARKETPLACE_NAME"

# Clean plugin cache
CACHE_DIR="$HOME/.claude/plugins/cache/$MARKETPLACE_NAME"
if [ -d "$CACHE_DIR" ]; then
    echo -e "${YELLOW}Removing cached plugin...${NC}"
    rm -rf "$CACHE_DIR"
fi

# Uninstall current plugin (ignore errors if not installed)
echo -e "${GREEN}Uninstalling current plugin...${NC}"
claude plugin uninstall "ijoka@$MARKETPLACE_NAME" 2>/dev/null || true

# Install from GitHub marketplace
echo -e "${GREEN}Installing plugin from GitHub marketplace...${NC}"
claude plugin install "ijoka@$MARKETPLACE_NAME"

echo ""
echo -e "${GREEN}=== Plugin update complete! ===${NC}"
echo -e "${YELLOW}Plugin installed from: https://github.com/$GITHUB_REPO${NC}"
echo -e "${YELLOW}Note: You may need to restart Claude Code for changes to take effect.${NC}"
