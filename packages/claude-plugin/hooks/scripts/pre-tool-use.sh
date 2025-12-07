#!/bin/bash
# PreToolUse hook wrapper
# 1. Smart feature matching (uses AI when available, falls back to keywords)
# 2. Validates feature_list.json edits

SCRIPT_DIR="$(dirname "$0")"
INPUT=$(cat)

# Run smart feature matching to activate appropriate feature
# Uses Haiku for intelligent classification when ANTHROPIC_API_KEY is available
MATCH_RESULT=$(echo "$INPUT" | uv run "$SCRIPT_DIR/smart-feature-match.py" 2>/dev/null)
MATCH_EXIT=$?

# If smart-match had output with hookSpecificOutput, pass it through
if [ -n "$MATCH_RESULT" ] && [ "$MATCH_EXIT" -eq 0 ]; then
    if echo "$MATCH_RESULT" | grep -q "hookSpecificOutput"; then
        echo "$MATCH_RESULT"
        exit 0
    fi
fi

# Then run validation (for feature_list.json edits)
echo "$INPUT" | uv run "$SCRIPT_DIR/validate-feature-edit.py"
