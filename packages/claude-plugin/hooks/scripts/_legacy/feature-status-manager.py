#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""
Intelligent Feature Status Manager

Automatically manages feature lifecycle:
1. Moves features to In Progress when work starts
2. Tracks completion criteria
3. Auto-completes features when criteria are met
"""

import json
import os
import sys
from pathlib import Path
from typing import TypedDict, Literal


class CompletionCriteria(TypedDict, total=False):
    type: Literal["build", "test", "lint", "manual", "any_success"]
    command_pattern: str  # Regex pattern to match against commands
    success_required: bool
    description: str


class Feature(TypedDict, total=False):
    category: str
    description: str
    steps: list[str]
    passes: bool
    inProgress: bool
    completionCriteria: CompletionCriteria


def load_features(project_dir: str) -> list[Feature] | None:
    """Load feature_list.json."""
    feature_file = Path(project_dir) / "feature_list.json"
    if not feature_file.exists():
        return None
    try:
        return json.loads(feature_file.read_text())
    except (json.JSONDecodeError, IOError):
        return None


def save_features(project_dir: str, features: list[Feature]) -> bool:
    """Save feature_list.json."""
    feature_file = Path(project_dir) / "feature_list.json"
    try:
        feature_file.write_text(json.dumps(features, indent=2))
        return True
    except IOError:
        return False


def get_active_feature_index(features: list[Feature]) -> int | None:
    """Get index of the active feature."""
    for i, f in enumerate(features):
        if f.get("inProgress"):
            return i
    return None


def check_completion_criteria(
    feature: Feature,
    tool_name: str,
    tool_input: dict,
    tool_result: dict
) -> tuple[bool, str]:
    """
    Check if a tool call satisfies the feature's completion criteria.
    Returns (is_complete, reason).
    """
    criteria = feature.get("completionCriteria", {})
    criteria_type = criteria.get("type", "manual")

    # Don't auto-complete if criteria is manual
    if criteria_type == "manual":
        return False, ""

    # Check if tool result indicates success
    is_error = tool_result.get("is_error", False)
    if is_error:
        return False, ""

    # Check based on criteria type
    if criteria_type == "build":
        if tool_name == "Bash":
            cmd = tool_input.get("command", "").lower()
            # Check for build commands
            if any(kw in cmd for kw in ["build", "compile", "cargo build", "pnpm build", "npm run build"]):
                return True, "Build succeeded"

    elif criteria_type == "test":
        if tool_name == "Bash":
            cmd = tool_input.get("command", "").lower()
            # Check for test commands
            if any(kw in cmd for kw in ["test", "pytest", "jest", "vitest", "cargo test"]):
                return True, "Tests passed"

    elif criteria_type == "lint":
        if tool_name == "Bash":
            cmd = tool_input.get("command", "").lower()
            if any(kw in cmd for kw in ["lint", "eslint", "prettier", "clippy"]):
                return True, "Lint passed"

    elif criteria_type == "any_success":
        # Complete on any successful "work" tool
        if tool_name in {"Edit", "Write", "Bash"} and not is_error:
            return True, "Work completed successfully"

    # Check command pattern if specified
    pattern = criteria.get("command_pattern", "")
    if pattern and tool_name == "Bash":
        import re
        cmd = tool_input.get("command", "")
        if re.search(pattern, cmd, re.IGNORECASE) and not is_error:
            return True, f"Pattern '{pattern}' matched and succeeded"

    return False, ""


def maybe_auto_complete(
    features: list[Feature],
    active_idx: int,
    tool_name: str,
    tool_input: dict,
    tool_result: dict
) -> str | None:
    """
    Check if the feature should be auto-completed based on the tool result.
    Returns a message if completed, None otherwise.
    """
    feature = features[active_idx]

    is_complete, reason = check_completion_criteria(
        feature, tool_name, tool_input, tool_result
    )

    if is_complete:
        # Mark feature as complete
        features[active_idx]["passes"] = True
        features[active_idx]["inProgress"] = False

        # Find and activate next incomplete feature
        next_idx = None
        for i, f in enumerate(features):
            if not f.get("passes") and i != active_idx:
                next_idx = i
                break

        if next_idx is not None:
            features[next_idx]["inProgress"] = True

        return f"Feature completed: {reason}"

    return None


def ensure_feature_in_progress(
    features: list[Feature],
    matched_idx: int
) -> str | None:
    """
    Ensure the matched feature is set to inProgress.
    Returns a message if status changed, None otherwise.
    """
    feature = features[matched_idx]

    # If already in progress, nothing to do
    if feature.get("inProgress"):
        return None

    # If feature is already complete, don't reactivate automatically
    if feature.get("passes"):
        return None

    # Clear any other inProgress features
    for f in features:
        f["inProgress"] = False

    # Set this feature to inProgress
    features[matched_idx]["inProgress"] = True

    return f"Started: {feature.get('description', 'Unknown')[:50]}"


def generate_completion_criteria(tool_name: str, tool_input: dict) -> CompletionCriteria:
    """
    Generate appropriate completion criteria based on the initial tool call.
    """
    if tool_name == "Edit" or tool_name == "Write":
        file_path = tool_input.get("file_path", "")

        # TypeScript/Vue files - need build to pass
        if any(ext in file_path for ext in [".ts", ".tsx", ".vue"]):
            return {
                "type": "build",
                "description": "Build must pass",
                "success_required": True
            }

        # Rust files - need cargo build
        if ".rs" in file_path:
            return {
                "type": "build",
                "command_pattern": "cargo (build|check)",
                "description": "Cargo build must pass",
                "success_required": True
            }

        # Python files - need tests or lint
        if ".py" in file_path:
            return {
                "type": "test",
                "command_pattern": "(pytest|python.*test)",
                "description": "Tests should pass",
                "success_required": True
            }

        # Test files specifically
        if "test" in file_path.lower() or "spec" in file_path.lower():
            return {
                "type": "test",
                "description": "Tests must pass",
                "success_required": True
            }

    elif tool_name == "Bash":
        cmd = tool_input.get("command", "").lower()

        # If starting with a test command, completion is test passing
        if any(kw in cmd for kw in ["test", "pytest", "jest"]):
            return {
                "type": "test",
                "description": "Tests must pass",
                "success_required": True
            }

        # If starting with build, completion is build passing
        if any(kw in cmd for kw in ["build", "compile"]):
            return {
                "type": "build",
                "description": "Build must pass",
                "success_required": True
            }

    # Default: any successful work completes the feature
    return {
        "type": "any_success",
        "description": "Any successful work tool",
        "success_required": True
    }


# Export for use by other scripts
if __name__ == "__main__":
    # Test mode
    print("Feature Status Manager loaded successfully")
