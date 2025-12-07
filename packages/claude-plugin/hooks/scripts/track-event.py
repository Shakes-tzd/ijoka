#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""
AgentKanban Event Tracker
Unified script for tracking tool calls, stops, and subagent events.
Links events to the active feature in feature_list.json.
"""

import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

SYNC_SERVER = os.environ.get("AGENTKANBAN_SERVER", "http://127.0.0.1:4000")


def get_active_feature(project_dir: str) -> dict | None:
    """Get the currently active feature (inProgress: true).

    Returns feature with ID in format 'project_dir:index' to match database storage.
    """
    feature_file = Path(project_dir) / "feature_list.json"
    if not feature_file.exists():
        return None

    try:
        features = json.loads(feature_file.read_text())
        for index, feature in enumerate(features):
            if feature.get("inProgress"):
                # ID format must match database: project_dir:index
                feature_id = f"{project_dir}:{index}"
                return {
                    "id": feature_id,
                    "description": feature.get("description"),
                    "category": feature.get("category", "functional")
                }
    except (json.JSONDecodeError, IOError):
        pass

    return None


def send_event(event_data: dict) -> bool:
    """Send event to AgentKanban server."""
    try:
        data = json.dumps(event_data).encode()
        req = Request(
            f"{SYNC_SERVER}/events",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except (URLError, TimeoutError, OSError):
        return False


def extract_file_paths(tool_input: dict) -> list[str]:
    """Extract file paths from tool input."""
    paths = []

    # Direct file_path
    if "file_path" in tool_input:
        paths.append(tool_input["file_path"])

    # Glob pattern
    if "pattern" in tool_input:
        paths.append(f"glob:{tool_input['pattern']}")

    # Bash command - extract paths heuristically
    if "command" in tool_input:
        cmd = tool_input["command"]
        # Just note the command type, don't parse all paths
        paths.append(f"bash:{cmd[:50]}...")

    return paths


def handle_post_tool_use(hook_input: dict, project_dir: str, session_id: str):
    """Handle PostToolUse events - track all tool calls."""
    tool_name = hook_input.get("tool_name", "unknown")
    tool_input = hook_input.get("tool_input", {})
    tool_result = hook_input.get("tool_result", {})

    # Skip tracking the tracking script itself
    if "track-event.py" in str(tool_input):
        return

    # Get active feature
    active_feature = get_active_feature(project_dir)

    # Build detailed payload based on tool type
    payload = {
        "filePaths": extract_file_paths(tool_input),
        "inputSummary": summarize_input(tool_name, tool_input),
        "success": not tool_result.get("is_error", False)
    }

    # Add tool-specific details
    if tool_name == "Edit":
        payload["oldString"] = (tool_input.get("old_string", "")[:200] + "...") if len(tool_input.get("old_string", "")) > 200 else tool_input.get("old_string", "")
        payload["newString"] = (tool_input.get("new_string", "")[:200] + "...") if len(tool_input.get("new_string", "")) > 200 else tool_input.get("new_string", "")
        payload["filePath"] = tool_input.get("file_path", "")
    elif tool_name == "Bash":
        payload["command"] = tool_input.get("command", "")[:500]
        payload["description"] = tool_input.get("description", "")
        # Include output preview if available
        output = tool_result.get("output", "")
        if output:
            payload["outputPreview"] = (output[:300] + "...") if len(output) > 300 else output
    elif tool_name == "Read":
        payload["filePath"] = tool_input.get("file_path", "")
        payload["offset"] = tool_input.get("offset")
        payload["limit"] = tool_input.get("limit")
    elif tool_name == "Write":
        payload["filePath"] = tool_input.get("file_path", "")
        content = tool_input.get("content", "")
        payload["contentPreview"] = (content[:200] + "...") if len(content) > 200 else content
    elif tool_name == "Grep":
        payload["pattern"] = tool_input.get("pattern", "")
        payload["path"] = tool_input.get("path", "")
        payload["glob"] = tool_input.get("glob", "")
    elif tool_name == "Glob":
        payload["pattern"] = tool_input.get("pattern", "")
        payload["path"] = tool_input.get("path", "")

    # Build event
    event = {
        "eventType": "ToolCall",
        "sourceAgent": "claude-code",
        "sessionId": session_id,
        "projectDir": project_dir,
        "toolName": tool_name,
        "payload": payload
    }

    if active_feature:
        event["featureId"] = active_feature["id"]
        event["payload"]["featureCategory"] = active_feature["category"]
        event["payload"]["featureDescription"] = active_feature["description"]

    send_event(event)


def handle_stop(hook_input: dict, project_dir: str, session_id: str):
    """Handle Stop events - agent finished."""
    stop_hook_input = hook_input.get("stop_hook_input", {})

    event = {
        "eventType": "AgentStop",
        "sourceAgent": "claude-code",
        "sessionId": session_id,
        "projectDir": project_dir,
        "payload": {
            "reason": stop_hook_input.get("stop_reason", "unknown"),
            "lastMessage": (stop_hook_input.get("last_assistant_message", "") or "")[:200]
        }
    }

    send_event(event)


def handle_subagent_stop(hook_input: dict, project_dir: str, session_id: str):
    """Handle SubagentStop events - Task tool finished."""
    tool_input = hook_input.get("tool_input", {})
    tool_result = hook_input.get("tool_result", {})

    event = {
        "eventType": "SubagentStop",
        "sourceAgent": "claude-code",
        "sessionId": session_id,
        "projectDir": project_dir,
        "toolName": "Task",
        "payload": {
            "taskDescription": tool_input.get("description", ""),
            "subagentType": tool_input.get("subagent_type", ""),
            "success": not tool_result.get("is_error", False),
            "resultSummary": (str(tool_result.get("output", ""))[:200] if tool_result else "")
        }
    }

    active_feature = get_active_feature(project_dir)
    if active_feature:
        event["featureId"] = active_feature["id"]
        event["payload"]["featureDescription"] = active_feature["description"]

    send_event(event)


def handle_user_prompt_submit(hook_input: dict, project_dir: str, session_id: str):
    """Handle UserPromptSubmit events - capture user queries for observability."""
    # Extract user prompt from hook input
    user_prompt = hook_input.get("user_prompt", "")
    if not user_prompt:
        # Try alternative field names
        user_prompt = hook_input.get("prompt", "") or hook_input.get("message", "")

    event = {
        "eventType": "UserQuery",
        "sourceAgent": "claude-code",
        "sessionId": session_id,
        "projectDir": project_dir,
        "payload": {
            "prompt": user_prompt[:1000],  # Truncate long prompts
            "promptLength": len(user_prompt),
            "preview": user_prompt[:200] if user_prompt else ""
        }
    }

    # Get active feature
    active_feature = get_active_feature(project_dir)
    if active_feature:
        event["featureId"] = active_feature["id"]
        event["payload"]["featureDescription"] = active_feature["description"]

    send_event(event)


def summarize_input(tool_name: str, tool_input: dict) -> str:
    """Create a brief summary of the tool input."""
    if tool_name == "Read":
        return f"Read: {tool_input.get('file_path', 'unknown')}"
    elif tool_name == "Write":
        return f"Write: {tool_input.get('file_path', 'unknown')}"
    elif tool_name == "Edit":
        return f"Edit: {tool_input.get('file_path', 'unknown')}"
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return f"Bash: {cmd[:60]}..." if len(cmd) > 60 else f"Bash: {cmd}"
    elif tool_name == "Glob":
        return f"Glob: {tool_input.get('pattern', 'unknown')}"
    elif tool_name == "Grep":
        return f"Grep: {tool_input.get('pattern', 'unknown')}"
    elif tool_name == "Task":
        return f"Task: {tool_input.get('description', 'unknown')}"
    else:
        return f"{tool_name}: {str(tool_input)[:60]}"


def main():
    # Get hook type from environment (set by wrapper or hooks.json)
    hook_type = os.environ.get("AGENTKANBAN_HOOK_TYPE", "PostToolUse")

    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": hook_type}}))
        return

    # Get session_id from hook input or environment
    session_id = hook_input.get("session_id") or os.environ.get("CLAUDE_SESSION_ID", "unknown")

    # Get project directory from environment (Claude Code sets this)
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if not project_dir:
        # Fallback: try to detect from tool input file paths
        tool_input = hook_input.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if file_path:
            path = Path(file_path)
            for parent in [path] + list(path.parents):
                if (parent / "feature_list.json").exists():
                    project_dir = str(parent)
                    break

    if not project_dir:
        project_dir = os.getcwd()

    # Route to appropriate handler
    if hook_type == "PostToolUse":
        handle_post_tool_use(hook_input, project_dir, session_id)
    elif hook_type == "Stop":
        handle_stop(hook_input, project_dir, session_id)
    elif hook_type == "SubagentStop":
        handle_subagent_stop(hook_input, project_dir, session_id)
    elif hook_type == "UserPromptSubmit":
        handle_user_prompt_submit(hook_input, project_dir, session_id)

    # Always continue - include hookEventName in hookSpecificOutput
    print(json.dumps({"hookSpecificOutput": {"hookEventName": hook_type}}))


if __name__ == "__main__":
    main()
