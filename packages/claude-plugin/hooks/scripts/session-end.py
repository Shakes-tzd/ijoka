#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["neo4j>=5.0"]
# ///
"""
Ijoka Session End Hook (SQLite Version)

Records session end in database.
"""

import json
import os
import sys
from pathlib import Path

# Import shared helpers
sys.path.insert(0, str(Path(__file__).parent))
import graph_db_helper as db_helper
from git_utils import resolve_project_path


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        hook_input = {}

    session_id = hook_input.get("session_id") or os.environ.get("CLAUDE_SESSION_ID", "unknown")

    # Resolve project path using git-aware resolution
    # In Ijoka, PROJECT = GIT REPOSITORY - all subdirectories belong to the same project
    project_dir = resolve_project_path(
        cwd=hook_input.get("cwd"),
        env_var=os.environ.get("CLAUDE_PROJECT_DIR")
    )

    # End session in database
    db_helper.end_session(session_id)

    # Record session end event (use session_id + event_type as unique ID for deduplication)
    db_helper.insert_event(
        event_type="SessionEnd",
        source_agent="claude-code",
        session_id=session_id,
        project_dir=project_dir,
        payload={"action": "session_ended"},
        event_id=f"{session_id}-SessionEnd"
    )

    # Output response
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionEnd"
        }
    }))


if __name__ == "__main__":
    main()
