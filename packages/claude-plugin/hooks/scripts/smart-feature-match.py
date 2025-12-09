#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["neo4j>=5.0"]
# ///
"""
Smart Feature Matching - Lightweight Version (No AI Subprocess)

Uses cached session state from UserPromptSubmit for feature classification.
Falls back to keyword matching only - NO Claude CLI subprocess calls.

This is the deterministic approach:
1. SessionStart: Inject active feature context
2. UserPromptSubmit: Classify once per user message (lightweight keywords)
3. PreToolUse: Use cached state, no classification
4. PostToolUse: Track work against active feature

NOTE: Uses Memgraph (graph_db_helper) as single source of truth.
"""

import json
import os
import sys
from pathlib import Path

# Import shared database helper (Memgraph)
sys.path.insert(0, str(Path(__file__).parent))
import graph_db_helper as db_helper


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        print('{"hookSpecificOutput": {"hookEventName": "PreToolUse"}}')
        return

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    session_id = hook_input.get("session_id") or os.environ.get("CLAUDE_SESSION_ID", "")

    # Get project directory
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if not project_dir:
        file_path = tool_input.get("file_path", "")
        if file_path:
            path = Path(file_path)
            for parent in [path] + list(path.parents):
                if (parent / "feature_list.json").exists():
                    project_dir = str(parent)
                    break

    if not project_dir:
        project_dir = os.getcwd()

    # Skip meta-tools entirely
    if tool_name in {"TodoRead", "TodoWrite", "Read", "Glob", "Grep"}:
        print('{"hookSpecificOutput": {"hookEventName": "PreToolUse"}}')
        return

    # --- Deterministic Feature Resolution ---
    # Priority 1: Use already active feature from database
    active_feature = db_helper.get_active_feature(project_dir)

    if active_feature and not active_feature.get("passes"):
        # Already have an active, incomplete feature - use it
        print('{"hookSpecificOutput": {"hookEventName": "PreToolUse"}}')
        return

    # Priority 2: Check session state cache (from UserPromptSubmit classification)
    if session_id:
        session_state = db_helper.get_session_state(session_id)
        if session_state and session_state.get("activeFeatureId"):
            cached_feature_id = session_state["activeFeatureId"]
            # Activate the cached feature if different
            if not active_feature or active_feature["id"] != cached_feature_id:
                db_helper.activate_feature(project_dir, cached_feature_id)
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": f"**Feature resumed from session cache**"
                    }
                }))
                return

    # Priority 3: No active feature - let UserPromptSubmit handle classification
    # Just output empty response, don't try to classify here
    print('{"hookSpecificOutput": {"hookEventName": "PreToolUse"}}')


if __name__ == "__main__":
    main()
