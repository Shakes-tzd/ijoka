#!/bin/bash
# PreToolUse hook wrapper - validates feature_list.json edits
uv run "$(dirname "$0")/validate-feature-edit.py"
