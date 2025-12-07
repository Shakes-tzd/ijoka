#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""
AgentKanban Feature Edit Validator
PreToolUse hook that validates Write/Edit operations on feature_list.json.
Blocks changes that would break the feature list structure.
"""

import json
import os
import sys
from pathlib import Path

VALID_CATEGORIES = {"infrastructure", "functional", "ui", "documentation", "testing", "security"}


def validate_feature_structure(features: list) -> tuple[bool, list[str]]:
    """Validate the feature list structure."""
    errors = []

    if not isinstance(features, list):
        return False, ["feature_list.json must be an array"]

    for i, feature in enumerate(features):
        prefix = f"Feature {i+1}"

        if not isinstance(feature, dict):
            errors.append(f"{prefix}: Must be an object")
            continue

        # Required fields
        if "description" not in feature:
            errors.append(f"{prefix}: Missing 'description'")
        elif not isinstance(feature["description"], str) or not feature["description"].strip():
            errors.append(f"{prefix}: 'description' must be non-empty string")

        if "category" not in feature:
            errors.append(f"{prefix}: Missing 'category'")
        elif feature["category"] not in VALID_CATEGORIES:
            errors.append(f"{prefix}: Invalid category '{feature['category']}'. Valid: {', '.join(sorted(VALID_CATEGORIES))}")

        if "passes" not in feature:
            errors.append(f"{prefix}: Missing 'passes'")
        elif not isinstance(feature["passes"], bool):
            errors.append(f"{prefix}: 'passes' must be boolean (true/false)")

        # Optional but validated if present
        if "steps" in feature and not isinstance(feature["steps"], list):
            errors.append(f"{prefix}: 'steps' must be an array")

        if "inProgress" in feature and not isinstance(feature["inProgress"], bool):
            errors.append(f"{prefix}: 'inProgress' must be boolean")

    return len(errors) == 0, errors


def check_no_deletions(old_features: list, new_features: list) -> tuple[bool, list[str]]:
    """Ensure no existing features were deleted."""
    old_descriptions = {f.get("description", "").lower() for f in old_features}
    new_descriptions = {f.get("description", "").lower() for f in new_features}

    deleted = old_descriptions - new_descriptions
    if deleted:
        return False, [f"Feature deleted (not allowed): {d}" for d in deleted]

    return True, []


def main():
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    # Read hook input
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        print('{"hookSpecificOutput": {"hookEventName": "PreToolUse"}}')
        return

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    # Only validate Write/Edit on feature_list.json
    file_path = tool_input.get("file_path", tool_input.get("path", ""))
    if not file_path.endswith("feature_list.json"):
        print('{"hookSpecificOutput": {"hookEventName": "PreToolUse"}}')
        return

    # For Write, validate the content directly
    if tool_name == "Write":
        content = tool_input.get("content", "")
        try:
            features = json.loads(content)
        except json.JSONDecodeError as e:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "decision": "block",
                    "reason": f"Invalid JSON: {e}"
                }
            }))
            return

        valid, errors = validate_feature_structure(features)
        if not valid:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "decision": "block",
                    "reason": "Invalid feature structure:\n- " + "\n- ".join(errors)
                }
            }))
            return

        # Check for deletions
        feature_file = Path(file_path)
        if feature_file.exists():
            try:
                old_features = json.loads(feature_file.read_text())
                ok, del_errors = check_no_deletions(old_features, features)
                if not ok:
                    print(json.dumps({
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "decision": "block",
                            "reason": "Feature deletion not allowed:\n- " + "\n- ".join(del_errors)
                        }
                    }))
                    return
            except (json.JSONDecodeError, IOError):
                pass  # Old file was invalid, allow overwrite

    # For Edit, we can't fully validate without applying the edit
    # Just do basic checks on the new_string if it looks like JSON
    elif tool_name == "Edit":
        new_string = tool_input.get("new_string", "")
        # If new_string contains passes, validate the boolean format
        if '"passes":' in new_string:
            if '"passes": true' not in new_string.lower() and '"passes": false' not in new_string.lower():
                # Check for invalid boolean strings
                if '"passes": "true"' in new_string or '"passes": "false"' in new_string:
                    print(json.dumps({
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "decision": "block",
                            "reason": "Invalid 'passes' value: must be boolean true/false, not string \"true\"/\"false\""
                        }
                    }))
                    return

    print('{"hookSpecificOutput": {"hookEventName": "PreToolUse"}}')


if __name__ == "__main__":
    main()
