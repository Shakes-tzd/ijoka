#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["neo4j>=5.0"]
# ///
"""
Ijoka Event Tracker

Unified script for tracking tool calls, stops, and subagent events.
Writes to Memgraph (graph database) as single source of truth.
Links events to the active feature.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Import shared database helper
sys.path.insert(0, str(Path(__file__).parent))
import graph_db_helper as db_helper

# Background shell cache for linking BashOutput to original commands
SHELL_CACHE_FILE = Path.home() / ".ijoka" / "background_shells.json"


# =============================================================================
# Stuckness Detection Functions
# =============================================================================

def detect_stuckness(session_id: str, feature_id: str, active_step: dict | None) -> tuple[bool, str]:
    """
    Detect if the agent is stuck.
    Returns (is_stuck, reason).
    """
    reasons = []

    # 1. Time since last meaningful progress
    last_progress = db_helper.get_last_meaningful_event(session_id)
    if last_progress:
        # Parse timestamp and calculate minutes since
        try:
            # Handle different timestamp formats from neo4j
            timestamp = last_progress.get("timestamp")
            if timestamp:
                if hasattr(timestamp, 'to_native'):
                    last_time = timestamp.to_native()
                else:
                    last_time = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))

                now = datetime.now(timezone.utc)
                minutes_since = (now - last_time).total_seconds() / 60

                if minutes_since > 5:
                    return True, f"No file changes for {int(minutes_since)} minutes"
                elif minutes_since > 3:
                    reasons.append(f"Slow progress ({int(minutes_since)} min since last change)")
        except Exception:
            pass  # Timestamp parsing failed, skip this check

    # 2. Repeated tool patterns (loops)
    recent_events = db_helper.get_recent_tool_patterns(session_id)
    pattern = db_helper.find_repeated_patterns(recent_events)
    if pattern and pattern.get("count", 0) >= 4:
        return True, f"Possible loop: {pattern.get('description', 'repeated tools')}"
    elif pattern and pattern.get("count", 0) >= 3:
        reasons.append(f"Repetitive pattern: {pattern.get('tool', '')} x{pattern.get('count', 0)}")

    # 3. Step stuck (in_progress for too long with little activity)
    if active_step:
        step_stats = db_helper.get_step_duration_stats(active_step.get("id", ""))
        minutes_active = step_stats.get("minutes_active", 0)
        event_count = step_stats.get("event_count", 0)

        # Step active for >15 min with <5 events = likely stuck
        if minutes_active > 15 and event_count < 5:
            return True, f"Step stalled: {minutes_active} min with only {event_count} events"
        # Step active for >10 min with <3 events = possibly stuck
        elif minutes_active > 10 and event_count < 3:
            reasons.append(f"Step slow: {minutes_active} min, {event_count} events")

    # If we have multiple warning signs but no definitive stuckness
    if len(reasons) >= 2:
        return True, "; ".join(reasons)

    return False, ""


def generate_stuckness_warning(reason: str) -> str:
    """Generate a user-friendly stuckness warning message."""
    return (
        f"You may be stuck: {reason}. "
        "Consider: What are you trying to accomplish? "
        "What's the next concrete step?"
    )


def get_shell_cache() -> dict:
    """Load the background shell cache."""
    try:
        if SHELL_CACHE_FILE.exists():
            with open(SHELL_CACHE_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_shell_cache(cache: dict):
    """Save the background shell cache."""
    try:
        SHELL_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SHELL_CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    except Exception:
        pass


def cache_background_shell(bash_id: str, command: str, description: str):
    """Cache a background shell's command info."""
    cache = get_shell_cache()
    cache[bash_id] = {
        "command": command,
        "description": description
    }
    # Keep cache size reasonable (last 50 shells)
    if len(cache) > 50:
        keys = list(cache.keys())
        for key in keys[:-50]:
            del cache[key]
    save_shell_cache(cache)


def get_cached_shell(bash_id: str) -> dict:
    """Get cached shell info by bash_id."""
    cache = get_shell_cache()
    return cache.get(bash_id, {})


def extract_file_paths(tool_input: dict) -> list[str]:
    """Extract file paths from tool input."""
    paths = []

    if "file_path" in tool_input:
        paths.append(tool_input["file_path"])

    if "pattern" in tool_input:
        paths.append(f"glob:{tool_input['pattern']}")

    if "command" in tool_input:
        cmd = tool_input["command"]
        paths.append(f"bash:{cmd[:50]}...")

    return paths


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
    elif tool_name.startswith("mcp__ijoka__"):
        # MCP ijoka tools - extract the action name
        action = tool_name.replace("mcp__ijoka__", "")
        # Include key parameters for context
        if "description" in tool_input:
            return f"ijoka.{action}: {tool_input['description'][:50]}"
        elif "feature_id" in tool_input:
            return f"ijoka.{action}: {tool_input['feature_id']}"
        else:
            return f"ijoka.{action}"
    else:
        return f"{tool_name}: {str(tool_input)[:60]}"


def check_completion_criteria(
    feature: dict,
    tool_name: str,
    tool_input: dict,
    tool_result: dict
) -> tuple[bool, str]:
    """Check if a tool call satisfies the feature's completion criteria."""
    import re

    criteria = feature.get("completionCriteria") or {}
    criteria_type = criteria.get("type", "manual")

    is_error = safe_get_result(tool_result, "is_error", False)
    if is_error:
        return False, ""

    if criteria_type == "build":
        if tool_name == "Bash":
            cmd = tool_input.get("command", "").lower()
            pattern = criteria.get("command_pattern", "")
            if pattern:
                if re.search(pattern, cmd, re.IGNORECASE):
                    return True, "Build passed"
            elif any(kw in cmd for kw in ["build", "compile", "cargo build", "pnpm build", "npm run build"]):
                return True, "Build passed"

    elif criteria_type == "test":
        if tool_name == "Bash":
            cmd = tool_input.get("command", "").lower()
            if any(kw in cmd for kw in ["test", "pytest", "jest", "vitest", "cargo test"]):
                return True, "Tests passed"

    elif criteria_type == "lint":
        if tool_name == "Bash":
            cmd = tool_input.get("command", "").lower()
            if any(kw in cmd for kw in ["lint", "eslint", "prettier", "clippy"]):
                return True, "Lint passed"

    elif criteria_type == "any_success":
        if tool_name in {"Edit", "Write", "Bash"}:
            return True, "Work completed"

    return False, ""


def maybe_auto_complete(
    project_dir: str,
    active_feature: dict,
    tool_name: str,
    tool_input: dict,
    tool_result: dict
) -> str | None:
    """Check if the active feature should be auto-completed. Returns status message."""
    if not active_feature:
        return None

    if active_feature.get("passes"):
        return None

    feature_id = active_feature["id"]
    is_work_tool = tool_name in {"Edit", "Write", "Bash", "Task"}
    is_error = safe_get_result(tool_result, "is_error", False)

    # Increment work count for successful work tools
    if is_work_tool and not is_error:
        new_work_count = db_helper.increment_work_count(feature_id)

        # Check work_count completion criteria
        criteria = active_feature.get("completionCriteria") or {}
        if criteria.get("type") == "work_count":
            threshold = criteria.get("count", 3)
            if new_work_count >= threshold:
                db_helper.complete_feature(feature_id)
                # Activate next feature
                _activate_next_feature(project_dir)
                return f"Auto-completed (work count: {new_work_count})"

    # Check other completion criteria
    is_complete, reason = check_completion_criteria(
        active_feature, tool_name, tool_input, tool_result
    )

    if is_complete:
        db_helper.complete_feature(feature_id)
        _activate_next_feature(project_dir)
        return f"Auto-completed: {reason}"

    return None


def _activate_next_feature(project_dir: str) -> str | None:
    """Activate the next incomplete feature. Returns its ID."""
    features = db_helper.get_features(project_dir)
    for feature in features:
        if not feature.get("passes") and not feature.get("inProgress"):
            db_helper.activate_feature(project_dir, feature["id"])
            return feature["id"]
    return None


def is_mcp_meta_tool(tool_name: str) -> bool:
    """Check if a tool call is an MCP ijoka meta tool (feature/project management)."""
    # MCP tools follow the pattern: mcp__<server>__<tool_name>
    return tool_name.startswith("mcp__ijoka__")


def is_diagnostic_command(tool_name: str, tool_input: dict) -> bool:
    """Check if a tool call is a diagnostic/meta command that shouldn't be feature-attributed."""
    # MCP ijoka tools are meta/management tools
    if is_mcp_meta_tool(tool_name):
        return True

    if tool_name == "Bash":
        cmd = tool_input.get("command", "").lower()
        # SQLite queries to ijoka database
        if "ijoka" in cmd and "sqlite3" in cmd:
            return True
        # Generic database inspection
        if any(x in cmd for x in [".ijoka", "session_state", "sessions", "features"]) and "select" in cmd:
            return True
        # Hook debugging/verification
        if "hook" in cmd and any(x in cmd for x in ["cat", "tail", "head", "grep"]):
            return True
    elif tool_name == "Read":
        file_path = tool_input.get("file_path", "").lower()
        # Reading hook scripts or logs
        if ".ijoka" in file_path or "hook" in file_path:
            return True
    return False


def generate_workflow_nudges(
    tool_name: str,
    tool_input: dict,
    tool_result: dict,
    project_dir: str,
    session_id: str,
    active_feature: dict | None,
    payload: dict | None = None,
    active_step: dict | None = None
) -> list[str]:
    """
    Generate workflow nudges based on current work patterns.
    Returns list of nudge messages to include in hook response.
    """
    nudges = []

    # Skip nudges for meta tools
    if is_mcp_meta_tool(tool_name) or is_diagnostic_command(tool_name, tool_input):
        return nudges

    # 1. Commit frequency nudge (after 5+ file changes)
    if tool_name in ("Edit", "Write"):
        try:
            work_stats = db_helper.get_work_since_last_commit(session_id, project_dir)
            if work_stats["work_count"] >= 5 and not db_helper.has_been_nudged(session_id, "commit_reminder"):
                nudges.append(f"💡 You've made {work_stats['work_count']} file changes. Consider committing your progress.")
                db_helper.record_nudge(session_id, "commit_reminder")
        except Exception:
            pass  # Don't fail the hook for nudge errors

    # 2. Feature completion nudge (after successful test/build)
    if tool_name == "Bash" and active_feature:
        cmd = tool_input.get("command", "").lower()
        is_error = safe_get_result(tool_result, "is_error", False)

        is_test_or_build = any(x in cmd for x in ["test", "pytest", "jest", "vitest", "build", "cargo build", "pnpm build"])

        if is_test_or_build and not is_error:
            if not db_helper.has_been_nudged(session_id, "feature_completion"):
                desc = active_feature.get("description", "")[:30]
                nudges.append(f"✅ Tests/build passed! If '{desc}...' is complete, use `ijoka_complete_feature`.")
                db_helper.record_nudge(session_id, "feature_completion")

    # 3. Drift warning (when drift score >= 0.7)
    if payload and active_step:
        drift_score = payload.get("driftScore", 0.0)
        drift_reason = payload.get("driftReason", "")

        if drift_score >= 0.7:
            step_id = active_step.get("id", "unknown")
            nudge_key = f"drift_warning_{step_id}"

            if not db_helper.has_been_nudged(session_id, nudge_key):
                warning = generate_drift_warning(active_step, drift_score, drift_reason)
                if warning:
                    nudges.append(warning)
                    db_helper.record_nudge(session_id, nudge_key)

    return nudges


def safe_get_result(tool_result, key: str, default=None):
    """Safely get a value from tool_result, handling both dict and list cases."""
    if isinstance(tool_result, dict):
        return tool_result.get(key, default)
    elif isinstance(tool_result, list):
        # For list results, we can't get specific keys - return default
        return default
    return default


def handle_todowrite(hook_input: dict, project_dir: str, session_id: str) -> list[str]:
    """
    Handle TodoWrite tool calls - sync todos to Step nodes.
    Returns any workflow nudges.
    """
    tool_input = hook_input.get("tool_input", {})
    todos = tool_input.get("todos", [])

    if not todos:
        return []

    # Get active feature
    active_feature = db_helper.get_active_feature(project_dir)
    if not active_feature:
        # No active feature - could auto-create one from todos
        # For now, just skip
        return []

    feature_id = active_feature["id"]

    # Sync todos to Steps
    step_ids = db_helper.sync_steps_from_todos(feature_id, todos)

    # Record PlanUpdate event
    payload = {
        "todoCount": len(todos),
        "stepIds": step_ids,
        "featureDescription": active_feature.get("description", ""),
        "todos": [{"content": t.get("content", ""), "status": t.get("status", "")} for t in todos[:10]]  # Limit payload size
    }

    # Create summary of plan state
    pending = sum(1 for t in todos if t.get("status") == "pending")
    in_progress = sum(1 for t in todos if t.get("status") == "in_progress")
    completed = sum(1 for t in todos if t.get("status") == "completed")

    summary = f"Plan updated: {completed}/{len(todos)} complete, {in_progress} in progress"

    db_helper.insert_event(
        event_type="PlanUpdate",
        source_agent="claude-code",
        session_id=session_id,
        project_dir=project_dir,
        tool_name="TodoWrite",
        payload=payload,
        feature_id=feature_id,
        success=True,
        summary=summary
    )

    return []


def handle_post_tool_use(hook_input: dict, project_dir: str, session_id: str) -> list[str]:
    """Handle PostToolUse events - track all tool calls. Returns workflow nudges."""
    tool_name = hook_input.get("tool_name", "unknown")
    tool_input = hook_input.get("tool_input", {})
    # Claude Code uses "tool_response", manual tests use "tool_result"
    tool_result = hook_input.get("tool_response") or hook_input.get("tool_result", {})
    # Use tool_use_id as event_id for deduplication
    tool_use_id = hook_input.get("tool_use_id")

    # Special handling for TodoWrite - capture plan structure
    if tool_name == "TodoWrite":
        return handle_todowrite(hook_input, project_dir, session_id)

    # Skip tracking the tracking script itself
    if "track-event.py" in str(tool_input) or "db_helper" in str(tool_input):
        return []

    # Check if this is a diagnostic/meta command
    is_diagnostic = is_diagnostic_command(tool_name, tool_input)
    is_meta_tool = is_mcp_meta_tool(tool_name)

    # Get the appropriate feature for this activity
    if is_meta_tool:
        # MCP ijoka tools go to the Session Work pseudo-feature
        active_feature = db_helper.get_or_create_session_work_feature(project_dir)
    elif is_diagnostic:
        # Other diagnostic commands don't get attributed to any feature
        active_feature = None
    else:
        # Normal tools get attributed to the active feature
        active_feature = db_helper.get_active_feature(project_dir)

    # Build detailed payload based on tool type
    payload = {
        "filePaths": extract_file_paths(tool_input),
        "inputSummary": summarize_input(tool_name, tool_input),
        "success": not safe_get_result(tool_result, "is_error", False),
        "isDiagnostic": is_diagnostic,
        "isMetaTool": is_meta_tool
    }

    # Add tool-specific details
    if tool_name == "Edit":
        payload["oldString"] = (tool_input.get("old_string", "")[:200] + "...") if len(tool_input.get("old_string", "")) > 200 else tool_input.get("old_string", "")
        payload["newString"] = (tool_input.get("new_string", "")[:200] + "...") if len(tool_input.get("new_string", "")) > 200 else tool_input.get("new_string", "")
        payload["filePath"] = tool_input.get("file_path", "")
        # Extract line numbers from the Edit response
        # Claude Code Edit responses typically include line info like "line 1455" or "lines 1455-1488"
        import re
        result_output = ""
        if tool_result:
            # tool_result can be dict with "output" key, or direct string/content
            if isinstance(tool_result, dict):
                result_output = tool_result.get("output", "") or tool_result.get("result", "") or ""
            elif isinstance(tool_result, str):
                result_output = tool_result
            elif isinstance(tool_result, list):
                # Sometimes response is a list of content blocks
                result_output = " ".join(str(item) for item in tool_result)
        # Extract line numbers from the "cat -n" output in Edit response
        # Format is like "  1234→line content" where 1234 is the line number
        line_matches = re.findall(r'^\s*(\d+)→', result_output, re.MULTILINE)
        if line_matches:
            # Get first and last line numbers from the snippet
            line_nums = [int(ln) for ln in line_matches]
            payload["startLine"] = min(line_nums)
            payload["endLine"] = max(line_nums)
    elif tool_name == "Bash":
        payload["command"] = tool_input.get("command", "")[:500]
        payload["description"] = tool_input.get("description", "")
        output = safe_get_result(tool_result, "output", "")
        if output:
            payload["outputPreview"] = (output[:300] + "...") if len(output) > 300 else output
        # Cache background shell info for later BashOutput lookups
        # Background shells have run_in_background=true and return a bash_id
        if tool_input.get("run_in_background"):
            # Extract bash_id from response - format varies
            bash_id = safe_get_result(tool_result, "bash_id", "")
            if not bash_id:
                # Try extracting from output text like "Background shell started with id: abc123"
                import re
                id_match = re.search(r'id[:\s]+([a-f0-9]+)', output or "", re.IGNORECASE)
                if id_match:
                    bash_id = id_match.group(1)
            if bash_id:
                cache_background_shell(
                    bash_id,
                    tool_input.get("command", ""),
                    tool_input.get("description", "")
                )
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
    elif tool_name == "BashOutput":
        bash_id = tool_input.get("bash_id", "")
        payload["bash_id"] = bash_id
        # Look up cached shell info to get original command context
        shell_info = get_cached_shell(bash_id)
        if shell_info:
            payload["originalCommand"] = shell_info.get("command", "")
            payload["commandDescription"] = shell_info.get("description", "")
    elif tool_name == "KillShell":
        payload["shell_id"] = tool_input.get("shell_id", "")

    # Add feature context if available
    feature_id = None
    if active_feature:
        feature_id = active_feature["id"]
        payload["featureCategory"] = active_feature["category"]
        payload["featureDescription"] = active_feature["description"]

    # Get active step for step-level tracking
    step_id = None
    active_step = None
    if active_feature and not is_diagnostic:
        active_step = db_helper.get_active_step(active_feature["id"])
        if active_step:
            step_id = active_step["id"]

    # Add step context to payload
    if active_step:
        payload["stepDescription"] = active_step.get("description", "")
        payload["stepOrder"] = active_step.get("step_order", 0)

    # Extract success status and summary for top-level Event fields
    is_success = not safe_get_result(tool_result, "is_error", False)
    summary = summarize_input(tool_name, tool_input)

    # Insert event into database (use tool_use_id for deduplication)
    db_helper.insert_event(
        event_type="ToolCall",
        source_agent="claude-code",
        session_id=session_id,
        project_dir=project_dir,
        tool_name=tool_name,
        payload=payload,
        feature_id=feature_id,
        step_id=step_id,
        success=is_success,
        summary=summary,
        event_id=tool_use_id
    )

    # Update session activity
    db_helper.update_session_activity(session_id)

    # Check for auto-completion after tracking the event
    completion_status = maybe_auto_complete(project_dir, active_feature, tool_name, tool_input, tool_result)
    if completion_status:
        # Record completion event
        completion_payload = {
            "completionStatus": completion_status,
            "triggeredBy": tool_name
        }
        if active_feature:
            completion_payload["featureDescription"] = active_feature["description"]

        db_helper.insert_event(
            event_type="FeatureCompleted",
            source_agent="claude-code",
            session_id=session_id,
            project_dir=project_dir,
            payload=completion_payload,
            feature_id=feature_id,
            success=True,
            summary=f"Feature completed: {completion_status}"
        )

    # Generate workflow nudges
    nudges = generate_workflow_nudges(
        tool_name, tool_input, tool_result,
        project_dir, session_id, active_feature,
        payload=payload, active_step=active_step
    )
    return nudges


def handle_stop(hook_input: dict, project_dir: str, session_id: str):
    """Handle Stop events - agent finished."""
    stop_hook_input = hook_input.get("stop_hook_input", {})
    stop_reason = stop_hook_input.get("stop_reason", "unknown")

    payload = {
        "reason": stop_reason,
        "lastMessage": (stop_hook_input.get("last_assistant_message", "") or "")[:200]
    }

    # Use session_id + event_type for deduplication (only one Stop per session)
    db_helper.insert_event(
        event_type="AgentStop",
        source_agent="claude-code",
        session_id=session_id,
        project_dir=project_dir,
        payload=payload,
        success=True,
        summary=f"Agent stopped: {stop_reason}",
        event_id=f"{session_id}-AgentStop"
    )


def handle_subagent_stop(hook_input: dict, project_dir: str, session_id: str):
    """Handle SubagentStop events - Task tool finished."""
    tool_input = hook_input.get("tool_input", {})
    # Claude Code uses "tool_response", manual tests use "tool_result"
    tool_result = hook_input.get("tool_response") or hook_input.get("tool_result", {})

    active_feature = db_helper.get_active_feature(project_dir)
    feature_id = active_feature["id"] if active_feature else None

    is_success = not safe_get_result(tool_result, "is_error", False)
    task_desc = tool_input.get("description", "unknown task")
    subagent_type = tool_input.get("subagent_type", "")

    payload = {
        "taskDescription": task_desc,
        "subagentType": subagent_type,
        "success": is_success,
        "resultSummary": (str(safe_get_result(tool_result, "output", ""))[:200] if tool_result else "")
    }

    if active_feature:
        payload["featureDescription"] = active_feature["description"]

    db_helper.insert_event(
        event_type="SubagentStop",
        source_agent="claude-code",
        session_id=session_id,
        project_dir=project_dir,
        tool_name="Task",
        payload=payload,
        feature_id=feature_id,
        success=is_success,
        summary=f"Subagent ({subagent_type}): {task_desc[:40]}"
    )


def classify_prompt_to_feature(prompt: str, features: list[dict]) -> tuple[int | None, int, str]:
    """
    Lightweight keyword-based classification of user prompt to feature.
    Returns (feature_index, confidence, reason).
    Only runs once per user message - no AI subprocess calls.
    """
    import re

    if not features or not prompt:
        return None, 0, "no_data"

    prompt_lower = prompt.lower()

    # Extract meaningful words from prompt
    stop_words = {
        'the', 'a', 'an', 'is', 'are', 'to', 'of', 'in', 'for', 'on', 'with',
        'can', 'you', 'please', 'help', 'me', 'this', 'that', 'it', 'i', 'we',
        'want', 'need', 'would', 'like', 'make', 'do', 'get', 'how', 'what'
    }
    words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_]{2,}\b', prompt_lower)
    prompt_keywords = {w for w in words if w not in stop_words}

    if not prompt_keywords:
        return None, 0, "no_keywords"

    best_idx = None
    best_score = 0.0
    best_matches = []

    for i, feature in enumerate(features):
        feature_text = (feature.get("description", "") + " " +
                       " ".join(feature.get("steps") or []))
        feature_words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_]{2,}\b', feature_text.lower())
        feature_keywords = {w for w in feature_words if w not in stop_words}

        # Count matching keywords
        matches = []
        for pw in prompt_keywords:
            for fw in feature_keywords:
                if pw == fw or pw.rstrip('s') == fw.rstrip('s'):
                    matches.append(pw)
                    break
                elif len(pw) > 4 and len(fw) > 4 and (pw in fw or fw in pw):
                    matches.append(pw)
                    break

        score = len(matches) / len(prompt_keywords) if prompt_keywords else 0

        # Boost incomplete features
        if not feature.get("passes"):
            score *= 1.3
        # Boost already active features (continuity)
        if feature.get("inProgress"):
            score *= 1.2

        if score > best_score:
            best_score = score
            best_idx = i
            best_matches = matches

    confidence = int(min(best_score * 100, 100))
    reason = f"keywords: {', '.join(best_matches[:3])}" if best_matches else "weak_match"

    return best_idx, confidence, reason


def handle_user_prompt_submit(hook_input: dict, project_dir: str, session_id: str):
    """
    Handle UserPromptSubmit events - capture user queries and classify features.
    This is the ONLY place feature classification happens (once per user message).
    """
    user_prompt = hook_input.get("user_prompt", "")
    if not user_prompt:
        user_prompt = hook_input.get("prompt", "") or hook_input.get("message", "")

    active_feature = db_helper.get_active_feature(project_dir)
    feature_id = active_feature["id"] if active_feature else None

    # --- Feature Classification (once per user message) ---
    features = db_helper.get_features(project_dir)
    classification_msg = None

    if features:
        # Check if we need to classify
        needs_classification = (
            active_feature is None or  # No active feature
            active_feature.get("passes")  # Current feature is complete
        )

        if needs_classification:
            matched_idx, confidence, reason = classify_prompt_to_feature(user_prompt, features)

            if matched_idx is not None and confidence >= 40:
                new_feature = features[matched_idx]
                new_feature_id = new_feature["id"]

                # Only switch if different from current
                if feature_id != new_feature_id:
                    db_helper.activate_feature(project_dir, new_feature_id)
                    feature_id = new_feature_id
                    active_feature = new_feature
                    classification_msg = f"Feature matched: {new_feature['description'][:40]}... ({confidence}%)"

        # Cache the session state
        db_helper.set_session_state(
            session_id=session_id,
            active_feature_id=feature_id,
            classification_source="user_prompt",
            last_prompt=user_prompt[:200]
        )

    payload = {
        "prompt": user_prompt[:1000],
        "promptLength": len(user_prompt),
        "preview": user_prompt[:200] if user_prompt else ""
    }

    if active_feature:
        payload["featureDescription"] = active_feature["description"]
    if classification_msg:
        payload["classificationResult"] = classification_msg

    # Create a short summary for the event
    prompt_preview = user_prompt[:50] + "..." if len(user_prompt) > 50 else user_prompt

    # Generate unique event ID based on session + prompt hash for deduplication
    import hashlib
    prompt_hash = hashlib.md5(user_prompt.encode()).hexdigest()[:8]
    event_id = f"{session_id}-UserQuery-{prompt_hash}"

    db_helper.insert_event(
        event_type="UserQuery",
        source_agent="claude-code",
        session_id=session_id,
        project_dir=project_dir,
        payload=payload,
        feature_id=feature_id,
        success=True,
        summary=f"User: {prompt_preview}",
        event_id=event_id
    )


def main():
    hook_type = os.environ.get("IJOKA_HOOK_TYPE", "PostToolUse")

    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": hook_type}}))
        return

    # Debug: log the hook input to see what session_id we're getting
    import sys as _sys
    import traceback as _tb
    debug_log = Path.home() / ".ijoka" / "hook_debug.log"
    with open(debug_log, "a") as f:
        f.write(f"\n=== {hook_type} at {__import__('datetime').datetime.now()} ===\n")
        f.write(f"hook_input keys: {list(hook_input.keys())}\n")
        f.write(f"session_id from input: {hook_input.get('session_id')}\n")
        f.write(f"cwd from input: {hook_input.get('cwd')}\n")
        f.write(f"CLAUDE_SESSION_ID env: {os.environ.get('CLAUDE_SESSION_ID')}\n")
        if hook_type == "PostToolUse":
            tool_name = hook_input.get("tool_name", "unknown")
            f.write(f"tool_name: {tool_name}\n")
            f.write(f"is_mcp_meta_tool: {is_mcp_meta_tool(tool_name)}\n")

    session_id = hook_input.get("session_id") or os.environ.get("CLAUDE_SESSION_ID", "unknown")
    # Claude Code provides 'cwd' in hook_input; fall back to env var or detection
    project_dir = hook_input.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR", "")

    if not project_dir:
        # Try to detect project from file path by looking for common project markers
        tool_input = hook_input.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if file_path:
            path = Path(file_path)
            for parent in [path] + list(path.parents):
                # Check for common project markers (git, package.json, Cargo.toml, etc.)
                if any((parent / marker).exists() for marker in [".git", "package.json", "Cargo.toml", "pyproject.toml", "CLAUDE.md"]):
                    project_dir = str(parent)
                    break

    if not project_dir:
        project_dir = os.getcwd()

    # Route to appropriate handler and collect nudges
    nudges = []
    if hook_type == "PostToolUse":
        nudges = handle_post_tool_use(hook_input, project_dir, session_id) or []
    elif hook_type == "Stop":
        handle_stop(hook_input, project_dir, session_id)
    elif hook_type == "SubagentStop":
        handle_subagent_stop(hook_input, project_dir, session_id)
    elif hook_type == "UserPromptSubmit":
        handle_user_prompt_submit(hook_input, project_dir, session_id)

    # Build response with optional nudges
    response = {"hookSpecificOutput": {"hookEventName": hook_type}}
    if nudges:
        response["hookSpecificOutput"]["additionalContext"] = "\n".join(nudges)

    print(json.dumps(response))


if __name__ == "__main__":
    main()
