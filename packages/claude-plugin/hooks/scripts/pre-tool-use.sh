#!/bin/bash
# PreToolUse hook wrapper
# 1. Auto-matches work to features (activates appropriate feature)
# 2. Validates feature_list.json edits

SCRIPT_DIR="$(dirname "$0")"
INPUT=$(cat)

# First, run auto-feature-match to activate appropriate feature
# This ensures work is tracked to the right feature
MATCH_RESULT=$(echo "$INPUT" | uv run "$SCRIPT_DIR/auto-feature-match.py" 2>/dev/null)
MATCH_EXIT=$?

# If auto-match had output, parse and potentially pass through
if [ -n "$MATCH_RESULT" ] && [ "$MATCH_EXIT" -eq 0 ]; then
    # Check if it contains hookSpecificOutput (auto-activated a feature)
    if echo "$MATCH_RESULT" | grep -q "hookSpecificOutput"; then
        # Output the match result (with the notification)
        echo "$MATCH_RESULT"
        exit 0
    fi
fi

# Then run validation (for feature_list.json edits)
echo "$INPUT" | uv run "$SCRIPT_DIR/validate-feature-edit.py"
