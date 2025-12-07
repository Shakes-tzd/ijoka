#!/bin/bash
# PostToolUse hook wrapper - tracks all tool calls
AGENTKANBAN_HOOK_TYPE=PostToolUse uv run "$(dirname "$0")/track-event.py"
