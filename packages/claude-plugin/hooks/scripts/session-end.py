#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["neo4j>=5.0"]
# ///
"""
Ijoka Session End Hook

Records session end in database and parses transcript for analytics.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Iterator, Any

# Import shared helpers
sys.path.insert(0, str(Path(__file__).parent))
import graph_db_helper as db_helper
from git_utils import resolve_project_path

# Import semantic analyzer for intelligent signal detection
try:
    from semantic_analyzer import get_session_logical_units, clear_logical_units
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False


# =============================================================================
# TRANSCRIPT PARSING (inline to avoid external dependencies)
# =============================================================================


def parse_timestamp(ts: Any) -> datetime:
    """Parse various timestamp formats."""
    if ts is None:
        return datetime.now()
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now()
    return datetime.now()


def parse_transcript_entry(data: dict) -> Optional[dict]:
    """Parse a single JSONL line into a transcript entry dict."""
    entry_type = data.get("type")

    if entry_type == "queue-operation":
        return {
            "type": entry_type,
            "timestamp": parse_timestamp(data.get("timestamp")).isoformat(),
            "operation": data.get("operation"),
        }

    if entry_type not in ("user", "assistant"):
        return None

    message = data.get("message", {})

    entry = {
        "type": entry_type,
        "timestamp": parse_timestamp(data.get("timestamp")).isoformat(),
        "uuid": data.get("uuid"),
        "parent_uuid": data.get("parentUuid"),
        "is_sidechain": data.get("isSidechain", False),
        "model": None,
        "content": None,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_tokens": 0,
        "cache_read_tokens": 0,
        "tool_calls": [],
        "stop_reason": None,
    }

    if entry_type == "user":
        content = message.get("content")
        if isinstance(content, str):
            entry["content"] = content
        elif isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            entry["content"] = "\n".join(text_parts) if text_parts else None

    elif entry_type == "assistant":
        entry["model"] = message.get("model")
        entry["stop_reason"] = message.get("stop_reason")

        # Token usage
        usage = message.get("usage", {})
        entry["input_tokens"] = usage.get("input_tokens", 0)
        entry["output_tokens"] = usage.get("output_tokens", 0)
        entry["cache_creation_tokens"] = usage.get("cache_creation_input_tokens", 0)
        entry["cache_read_tokens"] = usage.get("cache_read_input_tokens", 0)

        # Content blocks
        content = message.get("content", [])
        if isinstance(content, list):
            text_parts = []
            tool_calls = []
            for block in content:
                if isinstance(block, dict):
                    block_type = block.get("type")
                    if block_type == "text":
                        text_parts.append(block.get("text", ""))
                    elif block_type == "tool_use":
                        tool_calls.append({
                            "id": block.get("id", ""),
                            "name": block.get("name", ""),
                            "input": block.get("input", {}),
                        })
            entry["content"] = "\n".join(text_parts) if text_parts else None
            entry["tool_calls"] = tool_calls

    return entry


def parse_transcript_file(transcript_path: str) -> Iterator[dict]:
    """Parse a transcript JSONL file, yielding entry dicts."""
    path = Path(transcript_path)
    if not path.exists():
        return

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entry = parse_transcript_entry(data)
                if entry:
                    yield entry
            except (json.JSONDecodeError, Exception):
                continue


def sync_transcript_to_graph(
    session_id: str,
    project_dir: str,
    transcript_path: str
) -> dict:
    """
    Parse and sync a transcript to Memgraph.
    REFINED: Also detects patterns and auto-creates work items using semantic_analyzer.

    Returns dict with sync statistics and auto-created items.
    """
    path = Path(transcript_path)
    if not path.exists():
        return {"error": f"Transcript not found: {transcript_path}", "synced": 0}

    # Create TranscriptSession node
    db_helper.create_transcript_session(
        session_id=session_id,
        project_dir=project_dir,
        transcript_path=transcript_path,
        file_modified_at=datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    )

    # Parse and insert entries
    entry_count = 0
    tool_count = 0
    errors = []

    for entry in parse_transcript_file(transcript_path):
        try:
            tool_calls = entry.get("tool_calls")
            if tool_calls:
                tool_count += len(tool_calls)

            db_helper.insert_transcript_entry(
                session_id=session_id,
                entry_type=entry["type"],
                timestamp=entry["timestamp"],
                uuid=entry.get("uuid"),
                parent_uuid=entry.get("parent_uuid"),
                content=entry.get("content"),
                model=entry.get("model"),
                input_tokens=entry.get("input_tokens", 0),
                output_tokens=entry.get("output_tokens", 0),
                cache_creation_tokens=entry.get("cache_creation_tokens", 0),
                cache_read_tokens=entry.get("cache_read_tokens", 0),
                tool_calls=tool_calls if tool_calls else None,
                stop_reason=entry.get("stop_reason"),
                is_sidechain=entry.get("is_sidechain", False)
            )
            entry_count += 1

        except Exception as e:
            errors.append(str(e))
            if len(errors) > 10:
                break

    # After syncing transcript, detect patterns and auto-create work items
    active_feature = db_helper.get_active_feature(project_dir)
    active_feature_id = active_feature.get("id") if active_feature else None

    work_items_created = detect_and_create_work_items(
        session_id=session_id,
        project_dir=project_dir,
        active_feature_id=active_feature_id
    )

    return {
        "session_id": session_id,
        "entries_synced": entry_count,
        "tool_uses_synced": tool_count,
        "errors": errors[:5] if errors else [],
        "success": len(errors) == 0,
        "auto_created": work_items_created  # NEW: Report created items
    }


# =============================================================================
# SIGNAL DETECTION (uses semantic_analyzer classifications)
# =============================================================================


def detect_and_create_work_items(
    session_id: str,
    project_dir: str,
    active_feature_id: Optional[str] = None
) -> dict:
    """
    Analyze semantic_analyzer's Haiku classifications and auto-create work items.

    Uses existing logical_units classified during the session (no re-analysis).

    Returns:
        dict with auto-created items (bugs, spikes, features) or skip reason
    """
    if not SEMANTIC_AVAILABLE:
        return {"skipped": True, "reason": "semantic_analyzer not available"}

    created = {"bugs": [], "spikes": [], "features": []}

    # Get logical units classified by Haiku during the session
    logical_units = get_session_logical_units()

    if not logical_units:
        return {"skipped": True, "reason": "no logical units in session"}

    # Count by semantic type (already classified by Haiku!)
    type_counts = {}
    type_summaries = {}
    for unit in logical_units:
        t = unit.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
        type_summaries.setdefault(t, []).append(unit.get("summary", ""))

    # Decision: Auto-create work items based on patterns
    # These thresholds prevent noise from single occurrences

    # 1. Multiple bugfixes in session -> Create consolidated bug
    bugfix_count = type_counts.get("bugfix", 0)
    if bugfix_count >= 2:
        summaries = type_summaries.get("bugfix", [])[:3]
        bug_desc = f"Bugs fixed in session: {'; '.join(summaries)}"

        try:
            # Query active feature if not provided
            if not active_feature_id:
                active_feature = db_helper.get_active_feature(project_dir)
                active_feature_id = active_feature.get("id") if active_feature else None

            # Create bug via database
            bug_id = db_helper.create_feature(
                description=bug_desc,
                category="functional",
                feature_type="bug",
                priority=70,
                project_dir=project_dir
            )

            # Link to active feature as parent
            if active_feature_id and bug_id:
                db_helper.link_features(bug_id, active_feature_id)

            created["bugs"].append({
                "id": bug_id,
                "description": bug_desc,
                "parent_id": active_feature_id,
                "count": bugfix_count
            })
        except Exception:
            pass  # Don't fail hook for creation errors

    # 2. Schema changes -> Create feature for tracking
    schema_count = type_counts.get("schema_change", 0)
    if schema_count >= 1:
        summaries = type_summaries.get("schema_change", [])[:2]
        schema_desc = f"Schema changes: {'; '.join(summaries)}"

        try:
            if not active_feature_id:
                active_feature = db_helper.get_active_feature(project_dir)
                active_feature_id = active_feature.get("id") if active_feature else None

            # Create feature via database
            feature_id = db_helper.create_feature(
                description=schema_desc,
                category="functional",
                feature_type="feature",
                priority=80,  # High priority - schema changes need attention
                project_dir=project_dir
            )

            if active_feature_id and feature_id:
                db_helper.link_features(feature_id, active_feature_id)

            created["features"].append({
                "id": feature_id,
                "description": schema_desc,
                "parent_id": active_feature_id,
                "count": schema_count
            })
        except Exception:
            pass

    # 3. Lots of refactoring without clear feature -> Create spike
    # (suggests exploration/investigation happening)
    refactor_count = type_counts.get("refactor", 0)
    unknown_count = type_counts.get("unknown", 0)
    if refactor_count >= 3 or unknown_count >= 5:
        spike_desc = f"Investigation: {refactor_count} refactors, {unknown_count} unclassified changes"

        try:
            # Create spike via database
            spike_id = db_helper.create_feature(
                description=spike_desc,
                category="planning",
                feature_type="spike",
                priority=40,
                project_dir=project_dir
            )

            created["spikes"].append({
                "id": spike_id,
                "description": spike_desc,
                "refactor_count": refactor_count,
                "unknown_count": unknown_count
            })
        except Exception:
            pass

    # Clear logical units after processing (so next session starts fresh)
    try:
        clear_logical_units()
    except Exception:
        pass

    return created


# =============================================================================
# MAIN HOOK
# =============================================================================


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

    # Parse and sync transcript if available
    transcript_path = hook_input.get("transcript_path")
    transcript_result = None

    if transcript_path and Path(transcript_path).exists():
        try:
            transcript_result = sync_transcript_to_graph(
                session_id=session_id,
                project_dir=project_dir,
                transcript_path=transcript_path
            )
        except Exception as e:
            transcript_result = {"error": str(e), "synced": 0}

    # Output response
    response = {
        "hookSpecificOutput": {
            "hookEventName": "SessionEnd"
        }
    }

    if transcript_result:
        response["hookSpecificOutput"]["transcript"] = {
            "synced": transcript_result.get("success", False),
            "entries": transcript_result.get("entries_synced", 0),
            "tool_uses": transcript_result.get("tool_uses_synced", 0),
        }
        if transcript_result.get("errors"):
            response["hookSpecificOutput"]["transcript"]["errors"] = len(transcript_result["errors"])

        # Report auto-created work items from signal detection
        auto_created = transcript_result.get("auto_created", {})
        if auto_created and not auto_created.get("skipped"):
            bugs = auto_created.get("bugs", [])
            spikes = auto_created.get("spikes", [])
            features = auto_created.get("features", [])

            if bugs or spikes or features:
                created_summary = []
                if bugs:
                    created_summary.append(f"{len(bugs)} bug(s)")
                if spikes:
                    created_summary.append(f"{len(spikes)} spike(s)")
                if features:
                    created_summary.append(f"{len(features)} feature(s)")

                response["hookSpecificOutput"]["autoCreated"] = {
                    "summary": f"Auto-created: {', '.join(created_summary)}",
                    "bugs": bugs,
                    "spikes": spikes,
                    "features": features
                }

    print(json.dumps(response))


if __name__ == "__main__":
    main()
