#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["httpx"]
# ///
"""
Smart Feature Matching using Claude Haiku

Uses lightweight AI classification to match tool calls to the correct feature.
Falls back to keyword matching if API is unavailable.
"""

import json
import os
import sys
import re
import httpx
from pathlib import Path


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
SYNC_SERVER = os.environ.get("AGENTKANBAN_SERVER", "http://127.0.0.1:4000")


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


def build_tool_context(tool_name: str, tool_input: dict) -> str:
    """Build a concise context string from tool input."""
    parts = [f"Tool: {tool_name}"]

    if tool_name == "Edit" or tool_name == "Write" or tool_name == "Read":
        if fp := tool_input.get("file_path"):
            parts.append(f"File: {fp}")
        if tool_name == "Edit":
            if old := tool_input.get("old_string", "")[:100]:
                parts.append(f"Removing: {old}")
            if new := tool_input.get("new_string", "")[:100]:
                parts.append(f"Adding: {new}")
    elif tool_name == "Bash":
        if cmd := tool_input.get("command", "")[:200]:
            parts.append(f"Command: {cmd}")
        if desc := tool_input.get("description"):
            parts.append(f"Description: {desc}")
    elif tool_name == "Grep" or tool_name == "Glob":
        if pattern := tool_input.get("pattern"):
            parts.append(f"Pattern: {pattern}")
    elif tool_name == "Task":
        if desc := tool_input.get("description"):
            parts.append(f"Task: {desc}")
        if agent := tool_input.get("subagent_type"):
            parts.append(f"Agent: {agent}")

    return "\n".join(parts)


def classify_with_haiku(tool_context: str, features: list[dict], api_key: str) -> dict | None:
    """
    Use Claude Haiku to intelligently classify which feature the work belongs to.
    Returns: {"feature_index": int|None, "confidence": int, "reason": str, "should_create": bool}
    """
    # Build compact feature list
    feature_lines = []
    for i, f in enumerate(features):
        status = "DONE" if f.get("passes") else ("ACTIVE" if f.get("inProgress") else "TODO")
        feature_lines.append(f"{i}. [{status}] {f['description'][:80]}")

    feature_list_str = "\n".join(feature_lines)

    prompt = f"""You are a feature classifier for a development project. Analyze this tool call and determine which feature it relates to.

TOOL CALL:
{tool_context}

AVAILABLE FEATURES:
{feature_list_str}

Rules:
1. Match based on semantic meaning, not just keywords
2. Consider file paths, code content, and command context
3. If work clearly matches a TODO or ACTIVE feature, return that index
4. If work matches a DONE feature and seems like bug fix/enhancement, return that index
5. If work doesn't match any feature well, return null
6. Be conservative - only match if confident

Respond with ONLY valid JSON (no markdown):
{{"feature_index": <number or null>, "confidence": <0-100>, "reason": "<10 words max>", "should_create": <true if new feature needed>}}"""

    try:
        response = httpx.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-3-5-haiku-20241022",
                "max_tokens": 100,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=3.0  # Quick timeout - don't block tool execution
        )

        if response.status_code == 200:
            result = response.json()
            content = result["content"][0]["text"].strip()
            # Clean up response (remove markdown if present)
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
    except (httpx.TimeoutException, json.JSONDecodeError, KeyError, IndexError):
        pass

    return None


def keyword_fallback(tool_context: str, features: list[dict]) -> tuple[int | None, float]:
    """Fallback to keyword matching when AI is unavailable."""
    # Extract keywords from context
    stop_words = {
        'the', 'a', 'an', 'is', 'are', 'to', 'of', 'in', 'for', 'on', 'with',
        'file', 'path', 'src', 'true', 'false', 'null', 'none'
    }

    words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_]{2,}\b', tool_context.lower())
    context_keywords = {w for w in words if w not in stop_words}

    if not context_keywords:
        return None, 0.0

    best_idx = None
    best_score = 0.0

    for i, feature in enumerate(features):
        feature_text = feature.get("description", "") + " " + " ".join(feature.get("steps", []))
        feature_words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_]{2,}\b', feature_text.lower())
        feature_keywords = {w for w in feature_words if w not in stop_words}

        # Fuzzy matching
        matches = 0
        for cw in context_keywords:
            for fw in feature_keywords:
                if cw == fw or cw.rstrip('s') == fw.rstrip('s') or cw in fw or fw in cw:
                    matches += 1
                    break

        score = matches / len(context_keywords) if context_keywords else 0

        # Boost incomplete features
        if not feature.get("passes"):
            score *= 1.2

        if score > best_score:
            best_score = score
            best_idx = i

    return best_idx, best_score


def activate_feature(features: list[dict], index: int, reopen_if_complete: bool = False) -> str:
    """Activate a feature. Returns action taken."""
    # Clear all inProgress
    for f in features:
        f["inProgress"] = False

    target = features[index]
    action = "activated"

    if target.get("passes") and reopen_if_complete:
        target["passes"] = False
        action = "reopened"

    target["inProgress"] = True
    return action


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        print('{"continue": true}')
        return

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

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

    # Skip meta-tools
    if tool_name in {"TodoRead", "TodoWrite"}:
        print('{"continue": true}')
        return

    # Load features
    features = get_feature_list(project_dir)
    if not features:
        print('{"continue": true}')
        return

    # Build context for classification
    tool_context = build_tool_context(tool_name, tool_input)

    # Try AI classification first
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    classification = None

    if api_key and tool_name not in {"Read", "Glob", "Grep"}:  # Skip read-only for AI (save API calls)
        classification = classify_with_haiku(tool_context, features, api_key)

    matched_idx = None
    confidence = 0
    reason = ""

    if classification:
        matched_idx = classification.get("feature_index")
        confidence = classification.get("confidence", 0)
        reason = classification.get("reason", "AI classification")
    else:
        # Fallback to keyword matching
        matched_idx, score = keyword_fallback(tool_context, features)
        confidence = int(score * 100)
        reason = "keyword match"

    # Decide whether to activate
    # Higher threshold for switching from an already active feature
    current_active = next((i for i, f in enumerate(features) if f.get("inProgress")), None)

    if matched_idx is not None:
        should_switch = False

        if current_active is None:
            # No active feature - activate if confidence >= 30%
            should_switch = confidence >= 30
        elif current_active != matched_idx:
            # Different feature matched - only switch if high confidence
            should_switch = confidence >= 70

        if should_switch:
            feature = features[matched_idx]
            is_complete = feature.get("passes", False)
            action = activate_feature(features, matched_idx, reopen_if_complete=is_complete)
            save_feature_list(project_dir, features)

            desc = feature.get("description", "")[:50]
            print(json.dumps({
                "continue": True,
                "hookSpecificOutput": {
                    "additionalContext": f"**Feature {action}:** \"{desc}\" ({confidence}% - {reason})"
                }
            }))
            return

    print('{"continue": true}')


if __name__ == "__main__":
    main()
