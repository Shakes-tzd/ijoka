#!/bin/bash
# UserPromptSubmit hook - captures user queries for observability
AGENTKANBAN_HOOK_TYPE=UserPromptSubmit uv run "$(dirname "$0")/track-event.py"
