#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""
Auto Feature Matching Hook
Automatically matches tool calls to features and activates the appropriate feature.

This runs on PreToolUse to ensure work is properly tracked BEFORE it happens.
"""

import json
import os
import sys
import re
from pathlib import Path
from difflib import SequenceMatcher


def get_feature_list(project_dir: str) -> list[dict] | None:
    """Load feature_list.json if it exists."""
    feature_file = Path(project_dir) / "feature_list.json"
    if not feature_file.exists():
        return None
    try:
        return json.loads(feature_file.read_text())
    except (json.JSONDecodeError, IOError):
        return None


def save_feature_list(project_dir: str, features: list[dict]) -> bool:
    """Save feature_list.json."""
    feature_file = Path(project_dir) / "feature_list.json"
    try:
        feature_file.write_text(json.dumps(features, indent=2))
        return True
    except IOError:
        return False


def get_active_feature_index(features: list[dict]) -> int | None:
    """Get index of active feature."""
    for i, f in enumerate(features):
        if f.get("inProgress"):
            return i
    return None


def extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text."""
    # Remove common words and extract significant terms
    stop_words = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
        'ought', 'used', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
        'from', 'as', 'into', 'through', 'during', 'before', 'after', 'above',
        'below', 'between', 'under', 'again', 'further', 'then', 'once', 'and',
        'but', 'or', 'nor', 'so', 'yet', 'both', 'either', 'neither', 'not',
        'only', 'own', 'same', 'than', 'too', 'very', 'just', 'also', 'now',
        'file', 'path', 'dir', 'directory', 'src', 'test', 'tests', 'spec',
        'true', 'false', 'null', 'none', 'get', 'set', 'add', 'remove', 'update',
    }

    # Extract words (3+ chars, alphanumeric)
    words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_]{2,}\b', text.lower())

    # Filter stop words and return unique
    return {w for w in words if w not in stop_words}


def fuzzy_match(word1: str, word2: str) -> bool:
    """Check if two words are similar (handles plurals, prefixes)."""
    if word1 == word2:
        return True
    # Handle plurals and common suffixes
    if word1.rstrip('s') == word2.rstrip('s'):
        return True
    if word1.rstrip('ing') == word2 or word1 == word2.rstrip('ing'):
        return True
    if word1.rstrip('ed') == word2 or word1 == word2.rstrip('ed'):
        return True
    # Check if one contains the other (min 4 chars)
    if len(word1) >= 4 and len(word2) >= 4:
        if word1 in word2 or word2 in word1:
            return True
    return False


def similarity_score(keywords1: set[str], keywords2: set[str]) -> float:
    """Calculate similarity between two keyword sets with fuzzy matching."""
    if not keywords1 or not keywords2:
        return 0.0

    # Count fuzzy matches
    matches = 0
    for w1 in keywords1:
        for w2 in keywords2:
            if fuzzy_match(w1, w2):
                matches += 1
                break  # Count each keyword once

    # Similarity = matched / total input keywords
    # Weighted towards input keywords (what we're looking for)
    if not keywords1:
        return 0.0

    return matches / len(keywords1)


def match_feature(tool_input: dict, features: list[dict], tool_name: str) -> tuple[int | None, float]:
    """
    Match tool input to the most relevant feature.
    Returns (feature_index, confidence_score).
    """
    # Build text from tool input
    input_text_parts = []

    if tool_name == "Edit" or tool_name == "Write" or tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        input_text_parts.append(file_path)
        if tool_name == "Edit":
            input_text_parts.append(tool_input.get("old_string", ""))
            input_text_parts.append(tool_input.get("new_string", ""))
        elif tool_name == "Write":
            input_text_parts.append(tool_input.get("content", "")[:500])
    elif tool_name == "Bash":
        input_text_parts.append(tool_input.get("command", ""))
        input_text_parts.append(tool_input.get("description", ""))
    elif tool_name == "Grep" or tool_name == "Glob":
        input_text_parts.append(tool_input.get("pattern", ""))
        input_text_parts.append(tool_input.get("path", ""))
    elif tool_name == "Task":
        input_text_parts.append(tool_input.get("prompt", ""))
        input_text_parts.append(tool_input.get("description", ""))

    input_text = " ".join(str(p) for p in input_text_parts if p)
    input_keywords = extract_keywords(input_text)

    if not input_keywords:
        return None, 0.0

    best_match = None
    best_score = 0.0

    for i, feature in enumerate(features):
        # Build feature text
        feature_text = feature.get("description", "")
        steps = feature.get("steps", [])
        if steps:
            feature_text += " " + " ".join(steps)
        feature_text += " " + feature.get("category", "")

        feature_keywords = extract_keywords(feature_text)

        # Calculate similarity
        score = similarity_score(input_keywords, feature_keywords)

        # Bonus for incomplete features
        if not feature.get("passes"):
            score *= 1.2

        # Bonus if category matches common patterns
        category = feature.get("category", "").lower()
        if tool_name in ["Edit", "Write"] and category in ["functional", "ui", "refactoring"]:
            score *= 1.1
        elif tool_name == "Bash" and category in ["infrastructure", "testing"]:
            score *= 1.1

        if score > best_score:
            best_score = score
            best_match = i

    return best_match, best_score


def activate_feature(features: list[dict], index: int, reopen_if_complete: bool = False) -> bool:
    """
    Activate a feature by setting inProgress=true.
    Clears inProgress from other features.
    If reopen_if_complete is True and feature is complete, reopens it.
    """
    # Clear all inProgress first
    for f in features:
        f["inProgress"] = False

    target = features[index]

    # Handle completed features
    if target.get("passes") and reopen_if_complete:
        target["passes"] = False

    target["inProgress"] = True
    return True


def main():
    # Read hook input
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        print('{"continue": true}')
        return

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    # Get project directory from environment (set by Claude Code)
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if not project_dir:
        # Fallback: try to detect from tool input file paths
        file_path = tool_input.get("file_path", "")
        if file_path:
            # Find the project root by looking for feature_list.json
            path = Path(file_path)
            for parent in [path] + list(path.parents):
                if (parent / "feature_list.json").exists():
                    project_dir = str(parent)
                    break

    if not project_dir:
        project_dir = os.getcwd()

    # Only skip TodoRead/TodoWrite which are meta-tools
    skip_tools = {"TodoRead", "TodoWrite"}
    if tool_name in skip_tools:
        print('{"continue": true}')
        return

    # Load features
    features = get_feature_list(project_dir)
    if not features:
        print('{"continue": true}')
        return

    # Check if there's already an active feature
    active_idx = get_active_feature_index(features)
    if active_idx is not None:
        # Already have an active feature, continue
        print('{"continue": true}')
        return

    # No active feature - try to match
    matched_idx, confidence = match_feature(tool_input, features, tool_name)

    # Auto-activate if at least one keyword matches (confidence > 0.3 = 1 of 3 keywords)
    if matched_idx is not None and confidence >= 0.3:
        feature = features[matched_idx]
        description = feature.get("description", "Unknown")[:60]
        is_complete = feature.get("passes", False)

        # Auto-activate the matched feature
        if is_complete:
            # Reopen completed feature
            activate_feature(features, matched_idx, reopen_if_complete=True)
            save_feature_list(project_dir, features)

            # Inform user via hook output
            print(json.dumps({
                "continue": True,
                "hookSpecificOutput": {
                    "additionalContext": f"**Auto-reopened feature:** \"{description}\" (was complete, reopened for this work)"
                }
            }))
        else:
            # Activate incomplete feature
            activate_feature(features, matched_idx, reopen_if_complete=False)
            save_feature_list(project_dir, features)

            print(json.dumps({
                "continue": True,
                "hookSpecificOutput": {
                    "additionalContext": f"**Auto-activated feature:** \"{description}\" (matched with {confidence:.0%} confidence)"
                }
            }))
    else:
        # No good match - warn but continue
        # Don't block work, just note that it won't be tracked
        print('{"continue": true}')


if __name__ == "__main__":
    main()
