#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["neo4j>=5.0"]
# ///
"""
Ijoka Graph Database Helper

Shared module for all hooks to access Memgraph (source of truth).
Used by the ijoka CLI/API and hook scripts.

Architecture:
- Memgraph = Source of Truth (all writes go here)
- SQLite = Read cache for Tauri UI (synced from Memgraph)
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import time

from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable, AuthError, TransientError

# NOTE: Git utilities are in git_utils.py (no external dependencies)
# Import directly: `from git_utils import resolve_project_path`
# DO NOT import git functions from this module - they are not re-exported


# =============================================================================
# Connection Management
# =============================================================================

_driver: Optional[Driver] = None


def get_config() -> dict:
    """Get Memgraph connection config from environment or defaults."""
    return {
        "uri": os.environ.get("IJOKA_GRAPH_URI", "bolt://localhost:7687"),
        "user": os.environ.get("IJOKA_GRAPH_USER", ""),
        "password": os.environ.get("IJOKA_GRAPH_PASSWORD", ""),
        "database": os.environ.get("IJOKA_GRAPH_DATABASE", "memgraph"),
    }


def get_driver() -> Driver:
    """Get or create the Neo4j/Memgraph driver (singleton)."""
    global _driver
    if _driver is None:
        config = get_config()
        auth = (config["user"], config["password"]) if config["user"] else None
        _driver = GraphDatabase.driver(
            config["uri"],
            auth=auth,
            max_connection_pool_size=10,
            connection_acquisition_timeout=30.0,
        )
    return _driver


def close_driver() -> None:
    """Close the driver connection."""
    global _driver
    if _driver:
        _driver.close()
        _driver = None


def run_query(cypher: str, params: Optional[dict] = None) -> list[dict]:
    """Run a read query and return results."""
    driver = get_driver()
    config = get_config()
    with driver.session(database=config["database"]) as session:
        result = session.run(cypher, params or {})
        return [dict(record) for record in result]


def run_write_query(cypher: str, params: Optional[dict] = None, max_retries: int = 3) -> list[dict]:
    """Run a write query with retry on transaction conflicts."""
    driver = get_driver()
    config = get_config()

    for attempt in range(max_retries):
        try:
            with driver.session(database=config["database"]) as session:
                result = session.run(cypher, params or {})
                return [dict(record) for record in result]
        except TransientError as e:
            if attempt < max_retries - 1:
                # Exponential backoff: 0.1s, 0.2s, 0.4s
                time.sleep(0.1 * (2 ** attempt))
                continue
            raise  # Re-raise on final attempt
    return []  # Should not reach here


def is_connected() -> bool:
    """Check if we can connect to the graph database."""
    try:
        driver = get_driver()
        driver.verify_connectivity()
        return True
    except (ServiceUnavailable, AuthError, Exception):
        return False


# =============================================================================
# Helper Functions
# =============================================================================

def _node_to_dict(record: dict, key: str) -> dict:
    """Extract node properties from a query result."""
    node = record.get(key)
    if node is None:
        return {}
    # Handle both Node objects and dicts
    if hasattr(node, "items"):
        return dict(node.items())
    if hasattr(node, "_properties"):
        return dict(node._properties)
    return dict(node) if node else {}


def _now_iso() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Project Operations
# =============================================================================

def get_or_create_project(project_dir: str) -> dict:
    """Get existing project or create new one."""
    # Try to get existing
    results = run_query(
        "MATCH (p:Project {path: $path}) RETURN p",
        {"path": project_dir}
    )
    if results:
        return _node_to_dict(results[0], "p")

    # Create new project
    project_id = str(uuid.uuid4())
    name = os.path.basename(project_dir) or project_dir
    results = run_write_query(
        """
        CREATE (p:Project {
            id: $id,
            path: $path,
            name: $name,
            created_at: datetime(),
            updated_at: datetime()
        })
        RETURN p
        """,
        {"id": project_id, "path": project_dir, "name": name}
    )
    return _node_to_dict(results[0], "p") if results else {}


# =============================================================================
# Feature Operations
# =============================================================================

def get_features(project_dir: str) -> list[dict]:
    """Get all features for a project. Returns format compatible with db_helper."""
    results = run_query(
        """
        MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $projectPath})
        RETURN f
        ORDER BY f.priority DESC, f.created_at ASC
        """,
        {"projectPath": project_dir}
    )
    features = []
    for r in results:
        f = _node_to_dict(r, "f")
        # Convert graph status to db_helper format for compatibility
        status = f.get("status", "pending")
        f["passes"] = status == "complete"
        f["inProgress"] = status == "in_progress"
        f["workCount"] = f.get("work_count", 0)
        features.append(f)
    return features


def get_active_feature(project_dir: str) -> Optional[dict]:
    """Get the primary active feature, or first in_progress if no primary."""
    # First try to get the primary feature
    results = run_query(
        """
        MATCH (f:Feature {status: 'in_progress', is_primary: true})-[:BELONGS_TO]->(p:Project {path: $projectPath})
        RETURN f
        LIMIT 1
        """,
        {"projectPath": project_dir}
    )
    if results:
        f = _node_to_dict(results[0], "f")
        f["passes"] = False
        f["inProgress"] = True
        f["workCount"] = f.get("work_count", 0)
        return f

    # Fallback to any in_progress feature (highest priority)
    results = run_query(
        """
        MATCH (f:Feature {status: 'in_progress'})-[:BELONGS_TO]->(p:Project {path: $projectPath})
        RETURN f
        ORDER BY f.priority DESC
        LIMIT 1
        """,
        {"projectPath": project_dir}
    )
    if not results:
        return None
    f = _node_to_dict(results[0], "f")
    status = f.get("status", "pending")
    f["passes"] = status == "complete"
    f["inProgress"] = status == "in_progress"
    f["workCount"] = f.get("work_count", 0)
    return f


def get_active_features(project_dir: str) -> list[dict]:
    """Get ALL currently active (in_progress) features."""
    results = run_query(
        """
        MATCH (f:Feature {status: 'in_progress'})-[:BELONGS_TO]->(p:Project {path: $projectPath})
        RETURN f
        ORDER BY f.is_primary DESC, f.priority DESC
        """,
        {"projectPath": project_dir}
    )
    features = []
    for record in results:
        f = _node_to_dict(record, "f")
        f["passes"] = False
        f["inProgress"] = True
        f["workCount"] = f.get("work_count", 0)
        features.append(f)
    return features


# Type priority weights for attribution
_TYPE_PRIORITY = {
    "hotfix": 1.0,
    "bug": 0.8,
    "feature": 0.6,
    "spike": 0.4,
    "chore": 0.3,
    "epic": 0.2,
}


def score_attribution(
    features: list[dict],
    file_path: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_input: Optional[dict] = None,
) -> tuple[Optional[dict], float, str]:
    """
    Score features to determine which should receive event attribution.

    Uses a weighted scoring system:
    - File pattern match: 0.4 weight
    - Keyword overlap: 0.3 weight
    - Type priority: 0.2 weight
    - is_primary bonus: 0.1

    Returns:
        (best_feature, score, reason) or (None, 0, "no_match")
    """
    import re
    from fnmatch import fnmatch

    def extract_keywords(text: str) -> set[str]:
        if not text:
            return set()
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'to', 'of', 'in', 'for', 'on', 'with',
            'and', 'or', 'not', 'this', 'that', 'it', 'be', 'as', 'at', 'by',
            'from', 'has', 'have', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'add',
            'update', 'fix', 'implement', 'create', 'remove', 'delete', 'change'
        }
        words = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_]{2,}\b', text.lower())
        return {w for w in words if w not in stop_words}

    if not features:
        return None, 0.0, "no_features"

    # If only one feature, return it
    if len(features) == 1:
        return features[0], 1.0, "only_active"

    # Extract activity context
    activity_text = ""
    if file_path:
        activity_text += file_path + " "
    if tool_input:
        if tool_input.get("command"):
            activity_text += tool_input["command"] + " "
        if tool_input.get("pattern"):
            activity_text += tool_input["pattern"] + " "
        if tool_input.get("old_string"):
            activity_text += tool_input["old_string"][:200] + " "
        if tool_input.get("new_string"):
            activity_text += tool_input["new_string"][:200] + " "

    activity_keywords = extract_keywords(activity_text)

    best_feature = None
    best_score = 0.0
    best_reason = "no_match"

    for feature in features:
        score = 0.0
        reasons = []

        # 1. File pattern matching (0.4 weight)
        file_patterns = feature.get("file_patterns") or []
        if file_path and file_patterns:
            for pattern in file_patterns:
                if fnmatch(file_path, pattern) or pattern in file_path:
                    score += 0.4
                    reasons.append(f"pattern:{pattern}")
                    break

        # 2. Keyword overlap (0.3 weight)
        feature_keywords = extract_keywords(feature.get("description", ""))
        if feature_keywords and activity_keywords:
            overlap = len(feature_keywords & activity_keywords)
            total = max(len(feature_keywords), 1)
            keyword_score = min(overlap / total, 1.0) * 0.3
            if keyword_score > 0:
                score += keyword_score
                reasons.append(f"keywords:{overlap}/{total}")

        # 3. Type priority (0.2 weight)
        feature_type = feature.get("type", "feature")
        type_weight = _TYPE_PRIORITY.get(feature_type, 0.5)
        score += type_weight * 0.2

        # 4. Primary bonus (0.1)
        if feature.get("is_primary"):
            score += 0.1
            reasons.append("primary")

        if score > best_score:
            best_score = score
            best_feature = feature
            best_reason = "; ".join(reasons) if reasons else f"type:{feature_type}"

    # Require minimum score threshold
    if best_score < 0.15:
        return None, best_score, "below_threshold"

    return best_feature, best_score, best_reason


def get_or_create_session_work_feature(project_dir: str) -> dict:
    """
    Get or create the 'Session Work' pseudo-feature for meta/management activities.
    This feature captures activities like:
    - CLI commands (ijoka feature create, ijoka status, etc.)
    - Project configuration changes
    - Feature management operations

    The Session Work feature is special:
    - Category: 'infrastructure'
    - Never auto-completes
    - Always exists per project
    - Collects all meta-activities
    """
    SESSION_WORK_DESCRIPTION = "Session Work - Project management and meta activities"

    # Check if Session Work feature already exists
    results = run_query(
        """
        MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $projectPath})
        WHERE f.description = $description
        RETURN f
        LIMIT 1
        """,
        {"projectPath": project_dir, "description": SESSION_WORK_DESCRIPTION}
    )

    if results:
        f = _node_to_dict(results[0], "f")
        f["passes"] = False  # Never completes
        f["inProgress"] = False  # Not a real in-progress feature
        f["workCount"] = f.get("work_count", 0)
        return f

    # Create the Session Work feature
    feature_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Ensure project exists
    get_or_create_project(project_dir)

    run_write_query(
        """
        MATCH (p:Project {path: $projectPath})
        CREATE (f:Feature {
            id: $featureId,
            description: $description,
            category: 'infrastructure',
            status: 'pending',
            priority: -1,
            steps: ['Collects meta activities automatically'],
            work_count: 0,
            created_at: datetime($now),
            updated_at: datetime($now),
            is_session_work: true
        })-[:BELONGS_TO]->(p)
        """,
        {
            "projectPath": project_dir,
            "featureId": feature_id,
            "description": SESSION_WORK_DESCRIPTION,
            "now": now
        }
    )

    return {
        "id": feature_id,
        "description": SESSION_WORK_DESCRIPTION,
        "category": "infrastructure",
        "status": "pending",
        "priority": -1,
        "passes": False,
        "inProgress": False,
        "workCount": 0,
        "is_session_work": True
    }


def get_next_feature(project_dir: str) -> Optional[dict]:
    """Get the next pending feature (highest priority)."""
    results = run_query(
        """
        MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $projectPath})
        WHERE f.status = 'pending'
        AND NOT EXISTS {
            MATCH (f)-[:DEPENDS_ON {dependency_type: 'blocks'}]->(dep:Feature)
            WHERE dep.status <> 'complete'
        }
        RETURN f
        ORDER BY f.priority DESC, f.created_at ASC
        LIMIT 1
        """,
        {"projectPath": project_dir}
    )
    return _node_to_dict(results[0], "f") if results else None


def get_feature_by_branch(project_dir: str, branch: str) -> Optional[dict]:
    """Get a feature by its branch hint."""
    results = run_query(
        """
        MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $projectPath})
        WHERE f.branch_hint = $branch
        RETURN f
        LIMIT 1
        """,
        {"projectPath": project_dir, "branch": branch}
    )
    if not results:
        return None
    f = _node_to_dict(results[0], "f")
    # Convert graph status to db_helper format for compatibility
    status = f.get("status", "pending")
    f["passes"] = status == "complete"
    f["inProgress"] = status == "in_progress"
    f["workCount"] = f.get("work_count", 0)
    return f


def is_session_active(session_id: str, stale_minutes: int = 30) -> bool:
    """
    Check if a session is still active (has recent activity).
    A session is considered stale if it has no activity in the last N minutes.
    """
    if not session_id:
        return False

    duration_str = f"PT{stale_minutes}M"

    # Check Session node
    results = run_query(
        """
        MATCH (s:Session {id: $sessionId})
        RETURN s.last_activity > datetime() - duration($durationStr) as isActive
        """,
        {"sessionId": session_id, "durationStr": duration_str}
    )

    if results and results[0].get("isActive"):
        return True

    # Fallback: check recent events with this session_id
    event_results = run_query(
        """
        MATCH (e:Event {session_id: $sessionId})
        WHERE e.timestamp > datetime() - duration($durationStr)
        RETURN count(e) > 0 as hasRecent
        """,
        {"sessionId": session_id, "durationStr": duration_str}
    )

    return event_results[0].get("hasRecent", False) if event_results else False


def get_feature_claim(feature_id: str) -> Optional[dict]:
    """Get the current claim on a feature, if any."""
    results = run_query(
        """
        MATCH (f:Feature {id: $featureId})
        WHERE f.claiming_session_id IS NOT NULL
        RETURN f.claiming_session_id as sessionId,
               f.claiming_agent as agent,
               f.claimed_at as claimedAt
        """,
        {"featureId": feature_id}
    )

    if not results or not results[0].get("sessionId"):
        return None

    return {
        "session_id": results[0].get("sessionId"),
        "agent": results[0].get("agent"),
        "claimed_at": str(results[0].get("claimedAt", ""))
    }


def start_feature(
    feature_id: str,
    agent: Optional[str] = None,
    session_id: Optional[str] = None,
    force_override: bool = False
) -> Optional[dict]:
    """
    Start a feature (set status to 'in_progress') with claim tracking.

    Args:
        feature_id: Feature to start
        agent: Agent identifier
        session_id: Session identifier for claim tracking
        force_override: Override existing active claims

    Returns:
        Feature dict if successful, None if conflict or not found
    """
    session_id = session_id or f"session-{int(datetime.now().timestamp() * 1000)}"

    # Check for existing claim
    existing_claim = get_feature_claim(feature_id)
    if existing_claim and existing_claim["session_id"] != session_id:
        is_claim_active = is_session_active(existing_claim["session_id"])

        if is_claim_active and not force_override:
            # Conflict!
            return None

        # Stale claim - will be overridden

    results = run_write_query(
        """
        MATCH (f:Feature {id: $featureId})
        SET f.status = 'in_progress',
            f.assigned_agent = $agent,
            f.claiming_session_id = $sessionId,
            f.claiming_agent = $agent,
            f.claimed_at = datetime(),
            f.updated_at = datetime()
        RETURN f
        """,
        {"featureId": feature_id, "agent": agent, "sessionId": session_id}
    )
    return _node_to_dict(results[0], "f") if results else None


def complete_feature(feature_id: str) -> Optional[dict]:
    """Mark a feature as complete and clear claiming info."""
    results = run_write_query(
        """
        MATCH (f:Feature {id: $featureId})
        SET f.status = 'complete',
            f.completed_at = datetime(),
            f.updated_at = datetime(),
            f.claiming_session_id = null,
            f.claiming_agent = null,
            f.claimed_at = null
        RETURN f
        """,
        {"featureId": feature_id}
    )
    return _node_to_dict(results[0], "f") if results else None


def activate_feature(project_dir: str, feature_id: str) -> bool:
    """
    Activate a feature (set to in_progress).
    Multiple features can be in_progress simultaneously.
    Returns True if successful.
    """
    # Activate the target feature (no longer deactivates others)
    results = run_write_query(
        """
        MATCH (f:Feature {id: $featureId})
        SET f.status = 'in_progress', f.updated_at = datetime()
        RETURN f
        """,
        {"featureId": feature_id}
    )
    return len(results) > 0


def increment_work_count(feature_id: str) -> int:
    """Increment a feature's work count and return the new value."""
    results = run_write_query(
        """
        MATCH (f:Feature {id: $featureId})
        SET f.work_count = COALESCE(f.work_count, 0) + 1,
            f.updated_at = datetime()
        RETURN f.work_count as work_count
        """,
        {"featureId": feature_id}
    )
    if results:
        wc = results[0].get("work_count")
        # Handle neo4j Integer type
        return int(wc) if wc is not None else 0
    return 0


def create_feature(
    project_dir: str,
    description: str,
    category: str = "functional",
    steps: Optional[list[str]] = None,
    priority: int = 0,
    in_progress: bool = True,
    branch_hint: Optional[str] = None,
    file_patterns: Optional[list[str]] = None,
    work_item_type: str = "feature"
) -> str:
    """Create a new feature and return its ID."""
    feature_id = str(uuid.uuid4())

    # Ensure project exists
    get_or_create_project(project_dir)

    # Multiple features can be in_progress simultaneously (no deactivation needed)
    status = "in_progress" if in_progress else "pending"
    run_write_query(
        """
        MATCH (p:Project {path: $projectPath})
        CREATE (f:Feature {
            id: $id,
            description: $description,
            category: $category,
            type: $type,
            status: $status,
            priority: $priority,
            steps: $steps,
            branch_hint: $branchHint,
            file_patterns: $filePatterns,
            created_at: datetime(),
            updated_at: datetime(),
            work_count: 0
        })-[:BELONGS_TO]->(p)
        RETURN f
        """,
        {
            "projectPath": project_dir,
            "id": feature_id,
            "description": description,
            "category": category,
            "type": work_item_type,
            "status": status,
            "priority": priority,
            "steps": steps or [],
            "branchHint": branch_hint,
            "filePatterns": file_patterns or [],
        }
    )
    return feature_id


def reattribute_session_work_events(
    project_dir: str,
    feature_id: str,
    lookback_minutes: int = 60
) -> int:
    """
    Re-attribute recent Session Work events to a new feature (bidirectional linking).
    Events remain linked to Session Work AND get linked to the new feature.

    Args:
        project_dir: Project directory path
        feature_id: Feature to link events to
        lookback_minutes: How many minutes back to look for events

    Returns:
        Number of events re-attributed
    """
    # Work tool names (excludes meta/management tools)
    work_tool_names = [
        'Edit', 'Write', 'Read', 'Bash', 'Grep', 'Glob', 'Task',
        'TodoWrite', 'TodoRead', 'WebSearch', 'WebFetch', 'NotebookEdit'
    ]

    # Find events linked to Session Work within the lookback window
    # Memgraph uses ISO 8601 duration format: PT{minutes}M
    duration_str = f"PT{lookback_minutes}M"
    results = run_query(
        """
        MATCH (e:Event)-[:LINKED_TO]->(sw:Feature {is_session_work: true})-[:BELONGS_TO]->(p:Project {path: $projectPath})
        WHERE e.timestamp > datetime() - duration($durationStr)
        AND e.tool_name IN $workToolNames
        RETURN e.id as eventId
        """,
        {"projectPath": project_dir, "durationStr": duration_str, "workToolNames": work_tool_names}
    )

    if not results:
        return 0

    # Create LINKED_TO relationships to the new feature (bidirectional - keeps Session Work link)
    linked_count = 0
    for r in results:
        event_id = r.get("eventId")
        if event_id:
            run_write_query(
                """
                MATCH (e:Event {id: $eventId})
                MATCH (f:Feature {id: $featureId})
                MERGE (e)-[:LINKED_TO]->(f)
                """,
                {"eventId": event_id, "featureId": feature_id}
            )
            linked_count += 1

    # Update work_count on the new feature
    run_write_query(
        """
        MATCH (f:Feature {id: $featureId})
        SET f.work_count = f.work_count + $linkedCount,
            f.updated_at = datetime()
        """,
        {"featureId": feature_id, "linkedCount": linked_count}
    )

    return linked_count


def discover_feature(
    project_dir: str,
    description: str,
    category: str = "functional",
    steps: Optional[list[str]] = None,
    priority: int = 50,
    lookback_minutes: int = 60,
    mark_complete: bool = False,
    agent: Optional[str] = None,
    branch_hint: Optional[str] = None,
    work_item_type: str = "feature"
) -> dict:
    """
    Create a new feature on-demand and re-attribute recent Session Work activities.

    This is the Python equivalent of the `ijoka feature discover` CLI command.
    Use when Claude realizes mid-session that work constitutes a distinct feature.

    Args:
        project_dir: Project directory path
        description: Feature description
        category: Feature category
        steps: Implementation/verification steps
        priority: Priority (higher = more important)
        lookback_minutes: How many minutes back to look for activities
        mark_complete: If True, mark feature as complete immediately
        agent: Agent identifier
        branch_hint: Git branch name associated with this feature

    Returns:
        Dict with feature, reattributed_events count, and message
    """
    # Step 1: Create the feature
    feature_id = create_feature(
        project_dir=project_dir,
        description=description,
        category=category,
        steps=steps,
        priority=priority,
        in_progress=not mark_complete,  # Only start if not marking complete
        branch_hint=branch_hint,
        work_item_type=work_item_type
    )

    # Step 2: If mark_complete, complete it
    if mark_complete:
        complete_feature(feature_id)

    # Step 3: Re-attribute recent Session Work activities
    reattributed = reattribute_session_work_events(
        project_dir=project_dir,
        feature_id=feature_id,
        lookback_minutes=lookback_minutes
    )

    return {
        "feature_id": feature_id,
        "description": description,
        "category": category,
        "status": "complete" if mark_complete else "in_progress",
        "reattributed_events": reattributed,
        "lookback_minutes": lookback_minutes,
        "message": f"Discovered feature: {description}. Re-attributed {reattributed} events from last {lookback_minutes} minutes."
    }


def find_similar_feature(project_dir: str, description: str) -> Optional[dict]:
    """Find an existing feature with a similar description."""
    features = get_features(project_dir)
    desc_lower = description.lower()
    desc_words = set(desc_lower.split())

    for feature in features:
        existing_desc = (feature.get("description") or "").lower()

        # Exact match (case-insensitive)
        if existing_desc == desc_lower:
            return feature

        # High word overlap (> 60%)
        existing_words = set(existing_desc.split())
        if desc_words and existing_words:
            overlap = len(desc_words & existing_words)
            max_len = max(len(desc_words), len(existing_words))
            if overlap / max_len > 0.6:
                return feature

        # Substring match
        if desc_lower in existing_desc or existing_desc in desc_lower:
            return feature

    return None


def classify_by_file_path(project_dir: str, file_path: str) -> Optional[dict]:
    """
    Classify a file path by matching against feature file_patterns.
    Uses fnmatch for glob pattern matching.

    Args:
        project_dir: Project directory path
        file_path: File path to classify (relative to project)

    Returns:
        Dict with feature_id and confidence, or None if no match
    """
    import fnmatch

    # Get all features with file_patterns
    features = get_features(project_dir)
    features_with_patterns = [
        f for f in features
        if f.get("file_patterns") and len(f.get("file_patterns", [])) > 0
    ]

    if not features_with_patterns:
        return None

    # Find best matching feature
    for feature in features_with_patterns:
        patterns = feature.get("file_patterns", [])
        for pattern in patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return {
                    "feature_id": feature.get("id"),
                    "confidence": 0.8
                }

    return None


# =============================================================================
# Step Operations (Plan-Aware Activity Tracking)
# =============================================================================

def create_step(
    feature_id: str,
    description: str,
    order: int,
    status: str = "pending",
    expected_tools: Optional[list] = None
) -> str:
    """Create a Step node linked to a Feature."""
    step_id = str(uuid.uuid4())
    try:
        results = run_write_query("""
            MATCH (f:Feature {id: $featureId})
            CREATE (s:Step {
                id: $stepId,
                description: $description,
                status: $status,
                step_order: $order,
                expected_tools: $expectedTools,
                created_at: datetime(),
                started_at: null,
                completed_at: null
            })-[:BELONGS_TO]->(f)
            RETURN s
        """, {
            "featureId": feature_id,
            "stepId": step_id,
            "description": description,
            "status": status,
            "order": order,
            "expectedTools": expected_tools or []
        })
        if results:
            print(f"[DEBUG] Created Step: id={step_id}, desc='{description[:50]}...', status={status}, order={order}, feature_id={feature_id}")
        else:
            print(f"[WARN] Step creation query returned empty results: id={step_id}, feature_id={feature_id}")
    except Exception as e:
        print(f"[ERROR] Failed to create Step: id={step_id}, feature_id={feature_id}, error={str(e)}")
        raise
    return step_id


def get_steps(feature_id: str) -> list:
    """Get all steps for a feature, ordered by step_order."""
    results = run_query("""
        MATCH (s:Step)-[:BELONGS_TO]->(f:Feature {id: $featureId})
        RETURN s
        ORDER BY s.step_order ASC
    """, {"featureId": feature_id})
    return [_node_to_dict(r, "s") for r in results]


def get_active_step(feature_id: str) -> Optional[dict]:
    """Get the currently active step (in_progress or first pending)."""
    # First try to get in_progress step
    results = run_query("""
        MATCH (s:Step)-[:BELONGS_TO]->(f:Feature {id: $featureId})
        WHERE s.status = 'in_progress'
        RETURN s
        ORDER BY s.step_order ASC
        LIMIT 1
    """, {"featureId": feature_id})

    if results:
        return _node_to_dict(results[0], "s")

    # Fall back to first pending step
    results = run_query("""
        MATCH (s:Step)-[:BELONGS_TO]->(f:Feature {id: $featureId})
        WHERE s.status = 'pending'
        RETURN s
        ORDER BY s.step_order ASC
        LIMIT 1
    """, {"featureId": feature_id})

    return _node_to_dict(results[0], "s") if results else None


def update_step_status(step_id: str, status: str) -> Optional[dict]:
    """Update a step's status. Valid statuses: pending, in_progress, completed, skipped."""
    now_field = "started_at" if status == "in_progress" else "completed_at" if status == "completed" else None

    try:
        if now_field:
            results = run_write_query(f"""
                MATCH (s:Step {{id: $stepId}})
                SET s.status = $status,
                    s.{now_field} = datetime()
                RETURN s
            """, {"stepId": step_id, "status": status})
        else:
            results = run_write_query("""
                MATCH (s:Step {id: $stepId})
                SET s.status = $status
                RETURN s
            """, {"stepId": step_id, "status": status})

        if results:
            print(f"[DEBUG] Updated Step status: id={step_id}, status={status}")
        return _node_to_dict(results[0], "s") if results else None
    except Exception as e:
        print(f"[ERROR] Failed to update Step status: id={step_id}, status={status}, error={str(e)}")
        raise


def get_recent_events_for_step(step_id: str, limit: int = 5) -> list[dict]:
    """Get recent events linked to a step."""
    results = run_query("""
        MATCH (e:Event)-[:PART_OF_STEP]->(s:Step {id: $stepId})
        RETURN e
        ORDER BY e.timestamp DESC
        LIMIT $limit
    """, {"stepId": step_id, "limit": limit})
    return [_node_to_dict(r, "e") for r in results]


def count_unrelated_events(step_id: str) -> int:
    """Count recent events in last 10 minutes for sustained drift check."""
    results = run_query("""
        MATCH (e:Event)-[:PART_OF_STEP]->(s:Step {id: $stepId})
        WHERE e.timestamp > datetime() - duration('PT10M')
        RETURN count(e) as count
    """, {"stepId": step_id})
    return int(results[0]["count"]) if results else 0


def sync_steps_from_todos(feature_id: str, todos: list) -> list:
    """
    Sync Step nodes from TodoWrite payload.
    Creates new steps, updates existing, marks removed as skipped.
    Returns list of step IDs.
    """
    print(f"[DEBUG] sync_steps_from_todos: feature_id={feature_id}, todo_count={len(todos)}")

    existing_steps = get_steps(feature_id)
    existing_by_desc = {s.get("description", ""): s for s in existing_steps}
    print(f"[DEBUG] Found {len(existing_steps)} existing steps for feature {feature_id}")

    step_ids = []
    for i, todo in enumerate(todos):
        desc = todo.get("content", "")
        status_map = {"pending": "pending", "in_progress": "in_progress", "completed": "completed"}
        status = status_map.get(todo.get("status", "pending"), "pending")

        if desc in existing_by_desc:
            # Update existing step
            step = existing_by_desc[desc]
            print(f"[DEBUG] Updating existing step {step['id']}: status={status}")
            update_step_status(step["id"], status)
            step_ids.append(step["id"])
        else:
            # Create new step
            print(f"[DEBUG] Creating new step for todo {i}: desc='{desc[:50]}...', status={status}")
            step_id = create_step(feature_id, desc, i, status)
            step_ids.append(step_id)

    # Mark steps not in todos as skipped
    current_descs = {todo.get("content", "") for todo in todos}
    for step in existing_steps:
        if step.get("description", "") not in current_descs:
            print(f"[DEBUG] Marking step {step['id']} as skipped (no longer in todos)")
            update_step_status(step["id"], "skipped")

    print(f"[DEBUG] sync_steps_from_todos completed: created/updated {len(step_ids)} steps for feature {feature_id}")
    return step_ids


# =============================================================================
# StatusEvent Operations (Temporal Pattern)
# =============================================================================

def create_status_event(
    feature_id: str,
    from_status: str,
    to_status: str,
    triggered_by: str,
    session_id: Optional[str] = None,
    reason: Optional[str] = None
) -> str:
    """
    Create a StatusEvent node for audit trail (temporal pattern).
    Also updates the feature's status field for backward compatibility.
    """
    event_id = str(uuid.uuid4())
    now = _now_iso()

    run_write_query(
        """
        MATCH (f:Feature {id: $featureId})
        CREATE (se:StatusEvent {
            id: $eventId,
            from_status: $fromStatus,
            to_status: $toStatus,
            at: datetime($now),
            by: $triggeredBy,
            session_id: $sessionId,
            reason: $reason
        })-[:CHANGED_STATUS]->(f)
        SET f.status = $toStatus,
            f.updated_at = datetime($now)
        """,
        {
            "featureId": feature_id,
            "eventId": event_id,
            "fromStatus": from_status,
            "toStatus": to_status,
            "now": now,
            "triggeredBy": triggered_by,
            "sessionId": session_id,
            "reason": reason,
        }
    )
    return event_id


def get_feature_by_id(feature_id: str) -> Optional[dict]:
    """Get a feature by its ID."""
    results = run_query(
        "MATCH (f:Feature {id: $featureId}) RETURN f",
        {"featureId": feature_id}
    )
    if not results:
        return None
    f = _node_to_dict(results[0], "f")
    status = f.get("status", "pending")
    f["passes"] = status == "complete"
    f["inProgress"] = status == "in_progress"
    f["workCount"] = f.get("work_count", 0)
    return f


def auto_transition_to_in_progress(
    feature_id: str,
    triggered_by: str,
    session_id: Optional[str] = None
) -> bool:
    """
    Auto-transition a feature from 'pending' to 'in_progress' when first activity is linked.
    Returns True if transition happened, False if feature wasn't pending.
    """
    feature = get_feature_by_id(feature_id)
    if not feature:
        return False

    # Only transition if currently pending
    if feature.get("status") != "pending":
        return False

    # Skip auto-transition for Session Work feature
    if feature.get("is_session_work"):
        return False

    create_status_event(
        feature_id=feature_id,
        from_status="pending",
        to_status="in_progress",
        triggered_by=triggered_by,
        session_id=session_id,
        reason="Automatically started when first activity was linked"
    )
    return True


# =============================================================================
# Event Operations
# =============================================================================

def insert_event(
    event_type: str,
    source_agent: str,
    session_id: str,
    project_dir: str,
    tool_name: Optional[str] = None,
    payload: Optional[dict] = None,
    feature_id: Optional[str] = None,
    step_id: Optional[str] = None,
    success: bool = True,
    summary: Optional[str] = None,
    event_id: Optional[str] = None
) -> str:
    """Insert an event and return its ID. Now supports step linking."""
    if not event_id:
        event_id = str(uuid.uuid4())

    # Ensure project and session exist
    get_or_create_project(project_dir)

    # Create event linked to session (MERGE to prevent duplicates)
    cypher = """
        MATCH (p:Project {path: $projectPath})
        MERGE (s:Session {id: $sessionId})-[:IN_PROJECT]->(p)
        ON CREATE SET s.agent = $sourceAgent,
                      s.status = 'active',
                      s.started_at = datetime(),
                      s.last_activity = datetime(),
                      s.event_count = 0
        ON MATCH SET s.last_activity = datetime(),
                     s.event_count = s.event_count + 1
        MERGE (e:Event {id: $eventId})
        ON CREATE SET e.event_type = $eventType,
                      e.tool_name = $toolName,
                      e.payload = $payload,
                      e.timestamp = datetime(),
                      e.source_agent = $sourceAgent,
                      e.session_id = $sessionId,
                      e.success = $success,
                      e.summary = $summary
        MERGE (e)-[:TRIGGERED_BY]->(s)
    """
    params = {
        "projectPath": project_dir,
        "sessionId": session_id,
        "sourceAgent": source_agent,
        "eventId": event_id,
        "eventType": event_type,
        "toolName": tool_name,
        "payload": json.dumps(payload) if payload else None,
        "success": success,
        "summary": summary,
    }

    # Link to feature if provided
    if feature_id:
        cypher += """
        WITH e
        MATCH (f:Feature {id: $featureId})
        CREATE (e)-[:LINKED_TO]->(f)
        """
        params["featureId"] = feature_id

    # Link to step if provided
    if step_id:
        cypher += """
        WITH e
        MATCH (step:Step {id: $stepId})
        MERGE (e)-[:PART_OF_STEP]->(step)
        """
        params["stepId"] = step_id

    cypher += " RETURN e.id as id"

    run_write_query(cypher, params)

    # Auto-transition feature to in_progress if this is the first activity
    if feature_id:
        auto_transition_to_in_progress(
            feature_id=feature_id,
            triggered_by=f"auto:first_activity:{event_id}",
            session_id=session_id
        )

    return event_id


# =============================================================================
# Session Operations
# =============================================================================

def start_session(session_id: str, source_agent: str, project_dir: str) -> None:
    """Record a session start."""
    get_or_create_project(project_dir)
    run_write_query(
        """
        MATCH (p:Project {path: $projectPath})
        MERGE (s:Session {id: $sessionId})
        ON CREATE SET s.agent = $sourceAgent,
                      s.status = 'active',
                      s.started_at = datetime(),
                      s.last_activity = datetime(),
                      s.event_count = 0,
                      s.is_subagent = false
        ON MATCH SET s.status = 'active',
                     s.last_activity = datetime()
        MERGE (s)-[:IN_PROJECT]->(p)
        """,
        {
            "sessionId": session_id,
            "sourceAgent": source_agent,
            "projectPath": project_dir,
        }
    )


def end_session(session_id: str) -> None:
    """Mark a session as ended."""
    run_write_query(
        """
        MATCH (s:Session {id: $sessionId})
        SET s.status = 'ended',
            s.ended_at = datetime(),
            s.last_activity = datetime()
        """,
        {"sessionId": session_id}
    )


def update_session_activity(session_id: str) -> None:
    """Update a session's last_activity timestamp."""
    run_write_query(
        """
        MATCH (s:Session {id: $sessionId})
        SET s.last_activity = datetime()
        """,
        {"sessionId": session_id}
    )


def update_session_start_commit(session_id: str, commit_hash: str) -> bool:
    """Set the starting commit hash on a session."""
    cypher = '''
    MATCH (s:Session {id: $session_id})
    SET s.start_commit = $commit_hash
    RETURN true as success
    '''
    result = run_write_query(cypher, {
        "session_id": session_id,
        "commit_hash": commit_hash
    })
    return bool(result)


# =============================================================================
# Stats Operations
# =============================================================================

def get_stats(project_dir: Optional[str] = None) -> dict:
    """Get feature statistics."""
    if project_dir:
        results = run_query(
            """
            MATCH (p:Project {path: $projectPath})
            OPTIONAL MATCH (f:Feature)-[:BELONGS_TO]->(p)
            WITH p,
                 count(f) as total,
                 sum(CASE WHEN f.status = 'complete' THEN 1 ELSE 0 END) as completed,
                 sum(CASE WHEN f.status = 'in_progress' THEN 1 ELSE 0 END) as in_progress
            RETURN total, completed, in_progress
            """,
            {"projectPath": project_dir}
        )
    else:
        results = run_query(
            """
            MATCH (f:Feature)
            WITH count(f) as total,
                 sum(CASE WHEN f.status = 'complete' THEN 1 ELSE 0 END) as completed,
                 sum(CASE WHEN f.status = 'in_progress' THEN 1 ELSE 0 END) as in_progress
            RETURN total, completed, in_progress
            """
        )

    if not results:
        return {"total": 0, "completed": 0, "inProgress": 0, "percentage": 0}

    r = results[0]
    total = int(r.get("total") or 0)
    completed = int(r.get("completed") or 0)
    in_progress = int(r.get("in_progress") or 0)
    percentage = (completed / total * 100) if total > 0 else 0

    return {
        "total": total,
        "completed": completed,
        "inProgress": in_progress,
        "percentage": percentage,
    }


# =============================================================================
# Session State Cache (mirrors SQLite version for compatibility)
# =============================================================================

def get_session_state(session_id: str) -> Optional[dict]:
    """Get cached session state (feature classification)."""
    results = run_query(
        """
        MATCH (s:Session {id: $sessionId})
        RETURN s.active_feature_id as activeFeatureId,
               s.classified_at as classifiedAt,
               s.classification_source as classificationSource,
               s.last_prompt as lastPrompt
        """,
        {"sessionId": session_id}
    )
    if results and results[0].get("activeFeatureId"):
        return {
            "activeFeatureId": results[0].get("activeFeatureId"),
            "classifiedAt": str(results[0].get("classifiedAt") or ""),
            "classificationSource": results[0].get("classificationSource"),
            "lastPrompt": results[0].get("lastPrompt"),
        }
    return None


def set_session_state(
    session_id: str,
    active_feature_id: Optional[str],
    classification_source: str = "unknown",
    last_prompt: Optional[str] = None
) -> None:
    """Cache session state (feature classification result)."""
    run_write_query(
        """
        MATCH (s:Session {id: $sessionId})
        SET s.active_feature_id = $activeFeatureId,
            s.classified_at = datetime(),
            s.classification_source = $classificationSource,
            s.last_prompt = $lastPrompt
        """,
        {
            "sessionId": session_id,
            "activeFeatureId": active_feature_id,
            "classificationSource": classification_source,
            "lastPrompt": (last_prompt[:500] if last_prompt else None),
        }
    )


def clear_session_state(session_id: str) -> None:
    """Clear cached session state."""
    run_write_query(
        """
        MATCH (s:Session {id: $sessionId})
        SET s.active_feature_id = null,
            s.classified_at = null,
            s.classification_source = null,
            s.last_prompt = null
        """,
        {"sessionId": session_id}
    )


# =============================================================================
# Workflow Nudges - Track work patterns and suggest good practices
# =============================================================================

def get_work_since_last_commit(session_id: str, project_dir: str) -> dict:
    """
    Get count of work (Edit, Write) events since last git commit in this session.
    Used to nudge users to commit frequently.
    """
    results = run_query(
        """
        MATCH (s:Session {id: $sessionId})-[:IN_PROJECT]->(p:Project {path: $projectPath})
        OPTIONAL MATCH (e:Event)-[:TRIGGERED_BY]->(s)
        WHERE e.tool_name IN ['Edit', 'Write']

        // Find the most recent commit event in this session
        OPTIONAL MATCH (commit:Event)-[:TRIGGERED_BY]->(s)
        WHERE commit.tool_name = 'Bash'
        AND commit.payload CONTAINS 'git commit'

        WITH s, e, commit
        ORDER BY commit.timestamp DESC
        LIMIT 1

        WITH s, collect(e) as all_edits, commit

        // Count edits after the commit (or all if no commit)
        WITH s, all_edits, commit,
             [edit IN all_edits WHERE commit IS NULL OR edit.timestamp > commit.timestamp] as edits_since_commit

        RETURN size(edits_since_commit) as work_count,
               commit IS NOT NULL as has_committed,
               commit.timestamp as last_commit_time
        """,
        {"sessionId": session_id, "projectPath": project_dir}
    )

    if results:
        r = results[0]
        return {
            "work_count": int(r.get("work_count") or 0),
            "has_committed": bool(r.get("has_committed")),
            "last_commit_time": str(r.get("last_commit_time") or "")
        }
    return {"work_count": 0, "has_committed": False, "last_commit_time": ""}


def get_feature_work_duration(feature_id: str) -> dict:
    """
    Get how long a feature has been in_progress and activity stats.
    Used to detect stale features.
    """
    results = run_query(
        """
        MATCH (f:Feature {id: $featureId})
        OPTIONAL MATCH (se:StatusEvent)-[:CHANGED_STATUS]->(f)
        WHERE se.to_status = 'in_progress'
        WITH f, se
        ORDER BY se.at DESC
        LIMIT 1

        OPTIONAL MATCH (e:Event)-[:LINKED_TO]->(f)
        WITH f, se, count(e) as event_count, max(e.timestamp) as last_activity

        RETURN f.description as description,
               se.at as started_at,
               duration.between(se.at, datetime()).hours as hours_in_progress,
               event_count,
               last_activity
        """,
        {"featureId": feature_id}
    )

    if results:
        r = results[0]
        return {
            "description": r.get("description", ""),
            "started_at": str(r.get("started_at") or ""),
            "hours_in_progress": int(r.get("hours_in_progress") or 0),
            "event_count": int(r.get("event_count") or 0),
            "last_activity": str(r.get("last_activity") or "")
        }
    return {}


def record_nudge(session_id: str, nudge_type: str) -> None:
    """
    Record that a nudge was shown to prevent nagging.
    Nudge types: 'commit_reminder', 'feature_completion', 'drift_warning'
    """
    run_write_query(
        """
        MATCH (s:Session {id: $sessionId})
        SET s.nudges_shown = COALESCE(s.nudges_shown, []) + [$nudgeType],
            s.last_nudge_at = datetime()
        """,
        {"sessionId": session_id, "nudgeType": nudge_type}
    )


def has_been_nudged(session_id: str, nudge_type: str) -> bool:
    """Check if a nudge type has already been shown this session."""
    results = run_query(
        """
        MATCH (s:Session {id: $sessionId})
        RETURN $nudgeType IN COALESCE(s.nudges_shown, []) as nudged
        """,
        {"sessionId": session_id, "nudgeType": nudge_type}
    )
    return bool(results and results[0].get("nudged"))


def get_session_work_event_count(project_path: str, session_id: str) -> int:
    """Count events in Session Work for current session."""
    results = run_query(
        """
        MATCH (e:Event)-[:LINKED_TO]->(f:Feature)
        WHERE f.is_session_work = true
        AND e.session_id = $sessionId
        RETURN count(e) as count
        """,
        {"sessionId": session_id}
    )
    count = results[0].get("count", 0) if results else 0
    # Handle neo4j Integer type
    return int(count) if count is not None else 0


# =============================================================================
# Stuckness Detection Functions
# =============================================================================

def get_last_meaningful_event(session_id: str) -> Optional[dict]:
    """Get the last event that indicates real progress (Edit, Write with success)."""
    results = run_query("""
        MATCH (e:Event)-[:TRIGGERED_BY]->(s:Session {id: $sessionId})
        WHERE e.tool_name IN ['Edit', 'Write']
        AND e.success = true
        RETURN e
        ORDER BY e.timestamp DESC
        LIMIT 1
    """, {"sessionId": session_id})
    return _node_to_dict(results[0], "e") if results else None


def get_recent_tool_patterns(session_id: str, limit: int = 10) -> list[dict]:
    """Get recent tool calls for pattern analysis."""
    results = run_query("""
        MATCH (e:Event)-[:TRIGGERED_BY]->(s:Session {id: $sessionId})
        WHERE e.event_type = 'ToolCall'
        RETURN e.tool_name as tool_name,
               e.payload as payload,
               e.timestamp as timestamp
        ORDER BY e.timestamp DESC
        LIMIT $limit
    """, {"sessionId": session_id, "limit": limit})
    return [dict(r) for r in results]


def find_repeated_patterns(events: list[dict]) -> Optional[dict]:
    """
    Find repeated tool call patterns that indicate being stuck.
    Returns pattern info if found, None otherwise.
    """
    if len(events) < 3:
        return None

    # Group by tool_name
    tool_counts = {}
    tool_payloads = {}

    for event in events:
        tool = event.get("tool_name", "")
        if not tool:
            continue

        tool_counts[tool] = tool_counts.get(tool, 0) + 1

        # Track payload similarity
        payload_str = str(event.get("payload", ""))[:100]
        if tool not in tool_payloads:
            tool_payloads[tool] = []
        tool_payloads[tool].append(payload_str)

    # Check for repetition
    for tool, count in tool_counts.items():
        if count >= 3:
            # Check if payloads are similar (potential loop)
            payloads = tool_payloads[tool]
            if len(set(payloads)) <= 2:  # Very similar payloads
                return {
                    "tool": tool,
                    "count": count,
                    "description": f"{tool} called {count}x with similar args"
                }

    return None


def get_step_duration_stats(step_id: str) -> dict:
    """Get timing stats for a step."""
    results = run_query("""
        MATCH (s:Step {id: $stepId})
        OPTIONAL MATCH (e:Event)-[:PART_OF_STEP]->(s)
        WITH s, count(e) as event_count, max(e.timestamp) as last_activity
        RETURN s.started_at as started_at,
               s.status as status,
               event_count,
               last_activity
    """, {"stepId": step_id})

    if results:
        r = results[0]
        # Calculate minutes if started_at exists
        minutes = 0
        started = r.get("started_at")
        if started:
            try:
                if hasattr(started, 'to_native'):
                    from datetime import datetime, timezone
                    delta = datetime.now(timezone.utc) - started.to_native()
                    minutes = int(delta.total_seconds() / 60)
            except Exception:
                pass
        return {
            "started_at": str(started or ""),
            "status": r.get("status", ""),
            "event_count": int(r.get("event_count") or 0),
            "last_activity": str(r.get("last_activity") or ""),
            "minutes_active": minutes
        }
    return {}


# =============================================================================
# Commit Operations
# =============================================================================

def insert_commit(hash: str, message: str, author: str = None) -> Optional[str]:
    """Insert a Commit node into the graph."""
    cypher = '''
    MERGE (c:Commit {hash: $hash})
    ON CREATE SET
        c.id = $hash,
        c.message = $message,
        c.author = $author,
        c.timestamp = timestamp()
    RETURN c.id as id
    '''
    result = run_write_query(cypher, {
        "hash": hash,
        "message": message,
        "author": author
    })
    return result[0]["id"] if result else None


def link_commit_to_feature(commit_hash: str, feature_id: str) -> bool:
    """Create IMPLEMENTED_IN relationship from Commit to Feature."""
    cypher = '''
    MATCH (c:Commit {hash: $hash})
    MATCH (f:Feature {id: $feature_id})
    MERGE (c)-[:IMPLEMENTED_IN]->(f)
    RETURN true as success
    '''
    result = run_write_query(cypher, {
        "hash": commit_hash,
        "feature_id": feature_id
    })
    return bool(result)


def link_commit_to_session(commit_hash: str, session_id: str) -> bool:
    """Create MADE_COMMITS relationship from Session to Commit."""
    cypher = '''
    MATCH (c:Commit {hash: $hash})
    MATCH (s:Session {id: $session_id})
    MERGE (s)-[:MADE_COMMITS]->(c)
    RETURN true as success
    '''
    result = run_write_query(cypher, {
        "hash": commit_hash,
        "session_id": session_id
    })
    return bool(result)


def link_session_ancestry(new_session_id: str, prev_session_id: str) -> bool:
    """Create CONTINUED_FROM relationship between sessions."""
    cypher = '''
    MATCH (new:Session {id: $new_id})
    MATCH (prev:Session {id: $prev_id})
    MERGE (new)-[:CONTINUED_FROM]->(prev)
    RETURN true as success
    '''
    result = run_write_query(cypher, {
        "new_id": new_session_id,
        "prev_id": prev_session_id
    })
    return bool(result)


def get_previous_session(project_id: str, current_session_id: str) -> Optional[dict]:
    """Get the most recent previous session for a project."""
    cypher = '''
    MATCH (s:Session)
    WHERE s.project_id = $project_id AND s.id <> $current_id
    RETURN s.id as id, s.created_at as created_at
    ORDER BY s.created_at DESC
    LIMIT 1
    '''
    result = run_query(cypher, {
        "project_id": project_id,
        "current_id": current_session_id
    })
    return result[0] if result else None


def get_session_commits(session_id: str) -> list[dict]:
    """Get all commits made in a session."""
    cypher = '''
    MATCH (s:Session {id: $session_id})-[:MADE_COMMITS]->(c:Commit)
    RETURN c.hash as hash, c.message as message, c.timestamp as timestamp
    ORDER BY c.timestamp DESC
    '''
    return run_query(cypher, {"session_id": session_id})


def get_feature_commits(feature_id: str, limit: int = 3) -> list[dict]:
    """Get recent commits for a feature."""
    cypher = '''
    MATCH (f:Feature {id: $feature_id})<-[:IMPLEMENTED_IN]-(c:Commit)
    RETURN c.hash as hash, c.message as message, c.timestamp as timestamp
    ORDER BY c.timestamp DESC
    LIMIT $limit
    '''
    return run_query(cypher, {"feature_id": feature_id, "limit": limit})


# =============================================================================
# DEPRECATED - Import from feature_list.json
# =============================================================================
# This function is deprecated. The graph database is now the single source of truth.
# Use `ijoka feature create` CLI command instead.
# This function will be removed in a future version.

def sync_features_from_json(project_dir: str, features: list[dict]) -> None:
    """
    DEPRECATED: Import features from feature_list.json to graph database.

    WARNING: This function is deprecated and will be removed.
    The graph database is now the single source of truth.
    Use `ijoka feature create` CLI command instead.
    """
    import warnings
    warnings.warn(
        "sync_features_from_json is deprecated. Graph DB is the single source of truth.",
        DeprecationWarning,
        stacklevel=2
    )
    get_or_create_project(project_dir)

    for index, feature in enumerate(features):
        feature_id = f"{project_dir}:{index}"

        # Determine status from passes/inProgress flags
        if feature.get("passes"):
            status = "complete"
        elif feature.get("inProgress"):
            status = "in_progress"
        else:
            status = "pending"

        run_write_query(
            """
            MATCH (p:Project {path: $projectPath})
            MERGE (f:Feature {id: $featureId})
            ON CREATE SET f.description = $description,
                          f.category = $category,
                          f.status = $status,
                          f.priority = $priority,
                          f.steps = $steps,
                          f.work_count = $workCount,
                          f.created_at = datetime(),
                          f.updated_at = datetime()
            ON MATCH SET f.description = $description,
                         f.category = $category,
                         f.status = $status,
                         f.priority = $priority,
                         f.steps = $steps,
                         f.work_count = $workCount,
                         f.updated_at = datetime()
            MERGE (f)-[:BELONGS_TO]->(p)
            """,
            {
                "projectPath": project_dir,
                "featureId": feature_id,
                "description": feature.get("description", ""),
                "category": feature.get("category", "functional"),
                "status": status,
                "priority": feature.get("priority", 0),
                "steps": feature.get("steps") or [],
                "workCount": feature.get("workCount", 0),
            }
        )


# =============================================================================
# Transcript Operations
# =============================================================================


def create_transcript_session(
    session_id: str,
    project_dir: str,
    transcript_path: str,
    file_modified_at: Optional[str] = None
) -> str:
    """
    Create or update a TranscriptSession node.

    Links the transcript file to the Session node if it exists.
    A TranscriptSession represents the parsed data from a JSONL transcript file.
    """
    # Ensure Session exists
    get_or_create_project(project_dir)

    results = run_write_query(
        """
        MATCH (p:Project {path: $projectPath})
        MERGE (s:Session {id: $sessionId})-[:IN_PROJECT]->(p)
        ON CREATE SET s.status = 'ended',
                      s.started_at = datetime(),
                      s.last_activity = datetime(),
                      s.event_count = 0

        MERGE (ts:TranscriptSession {id: $sessionId})
        ON CREATE SET ts.transcript_path = $transcriptPath,
                      ts.file_modified_at = $fileModifiedAt,
                      ts.parsed_at = datetime(),
                      ts.entry_count = 0,
                      ts.total_input_tokens = 0,
                      ts.total_output_tokens = 0,
                      ts.total_cache_creation_tokens = 0,
                      ts.total_cache_read_tokens = 0
        ON MATCH SET ts.file_modified_at = $fileModifiedAt,
                     ts.parsed_at = datetime()

        MERGE (ts)-[:TRANSCRIPT_OF]->(s)
        RETURN ts.id as id
        """,
        {
            "sessionId": session_id,
            "projectPath": project_dir,
            "transcriptPath": transcript_path,
            "fileModifiedAt": file_modified_at
        }
    )
    return results[0]["id"] if results else session_id


def insert_transcript_entry(
    session_id: str,
    entry_type: str,
    timestamp: str,
    uuid: Optional[str] = None,
    parent_uuid: Optional[str] = None,
    content: Optional[str] = None,
    model: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
    tool_calls: Optional[list[dict]] = None,
    stop_reason: Optional[str] = None,
    is_sidechain: bool = False
) -> str:
    """
    Insert a TranscriptEntry node linked to TranscriptSession.

    Args:
        session_id: The transcript session ID
        entry_type: 'user', 'assistant', or 'queue-operation'
        timestamp: ISO timestamp of the entry
        uuid: Unique ID from transcript
        parent_uuid: Parent entry UUID (for threading)
        content: Text content (user message or assistant response)
        model: Model name (for assistant entries)
        input_tokens: Input token count
        output_tokens: Output token count
        cache_creation_tokens: Cache creation token count
        cache_read_tokens: Cache read token count
        tool_calls: List of tool call dicts [{name, id, input}]
        stop_reason: Stop reason (for assistant entries)
        is_sidechain: Whether this is a sidechain entry
    """
    entry_id = uuid or str(__import__("uuid").uuid4())

    cypher = """
        MATCH (ts:TranscriptSession {id: $sessionId})
        CREATE (e:TranscriptEntry {
            id: $entryId,
            entry_type: $entryType,
            timestamp: datetime($timestamp),
            uuid: $uuid,
            parent_uuid: $parentUuid,
            content: $content,
            model: $model,
            input_tokens: $inputTokens,
            output_tokens: $outputTokens,
            cache_creation_tokens: $cacheCreationTokens,
            cache_read_tokens: $cacheReadTokens,
            stop_reason: $stopReason,
            is_sidechain: $isSidechain,
            tool_call_count: $toolCallCount
        })-[:IN_TRANSCRIPT]->(ts)

        // Update aggregates on TranscriptSession
        SET ts.entry_count = ts.entry_count + 1,
            ts.total_input_tokens = ts.total_input_tokens + $inputTokens,
            ts.total_output_tokens = ts.total_output_tokens + $outputTokens,
            ts.total_cache_creation_tokens = ts.total_cache_creation_tokens + $cacheCreationTokens,
            ts.total_cache_read_tokens = ts.total_cache_read_tokens + $cacheReadTokens

        RETURN e.id as id
    """

    params = {
        "sessionId": session_id,
        "entryId": entry_id,
        "entryType": entry_type,
        "timestamp": timestamp,
        "uuid": uuid,
        "parentUuid": parent_uuid,
        "content": (content[:10000] if content else None),  # Truncate long content
        "model": model,
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "cacheCreationTokens": cache_creation_tokens,
        "cacheReadTokens": cache_read_tokens,
        "stopReason": stop_reason,
        "isSidechain": is_sidechain,
        "toolCallCount": len(tool_calls) if tool_calls else 0
    }

    results = run_write_query(cypher, params)

    # Create tool use nodes if present
    if tool_calls:
        for tc in tool_calls:
            insert_transcript_tool_use(
                entry_id=entry_id,
                tool_id=tc.get("id", ""),
                tool_name=tc.get("name", ""),
                tool_input=tc.get("input", {})
            )

    # Link to parent entry if present (conversation threading)
    if parent_uuid:
        run_write_query(
            """
            MATCH (e:TranscriptEntry {id: $entryId})
            MATCH (parent:TranscriptEntry {uuid: $parentUuid})
            MERGE (e)-[:REPLY_TO]->(parent)
            """,
            {"entryId": entry_id, "parentUuid": parent_uuid}
        )

    return entry_id


def insert_transcript_tool_use(
    entry_id: str,
    tool_id: str,
    tool_name: str,
    tool_input: dict
) -> str:
    """
    Insert a TranscriptToolUse node linked to a TranscriptEntry.
    """
    use_id = tool_id or str(__import__("uuid").uuid4())

    # Serialize input, truncate if too large
    input_json = json.dumps(tool_input)
    if len(input_json) > 5000:
        input_json = json.dumps({"truncated": True, "preview": str(tool_input)[:500]})

    run_write_query(
        """
        MATCH (e:TranscriptEntry {id: $entryId})
        CREATE (t:TranscriptToolUse {
            id: $useId,
            tool_name: $toolName,
            tool_input: $toolInput
        })-[:TOOL_IN_ENTRY]->(e)
        """,
        {
            "entryId": entry_id,
            "useId": use_id,
            "toolName": tool_name,
            "toolInput": input_json
        }
    )
    return use_id


def get_transcript_session(session_id: str) -> Optional[dict]:
    """Get a TranscriptSession with aggregate stats."""
    results = run_query(
        """
        MATCH (ts:TranscriptSession {id: $sessionId})
        OPTIONAL MATCH (ts)-[:TRANSCRIPT_OF]->(s:Session)
        OPTIONAL MATCH (s)-[:IN_PROJECT]->(p:Project)
        RETURN ts, s.agent as agent, p.path as project_path
        """,
        {"sessionId": session_id}
    )
    if not results:
        return None

    ts = _node_to_dict(results[0], "ts")
    ts["agent"] = results[0].get("agent")
    ts["project_path"] = results[0].get("project_path")
    return ts


def get_transcript_entries(
    session_id: str,
    entry_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> list[dict]:
    """
    Get transcript entries for a session.

    Args:
        session_id: Transcript session ID
        entry_type: Filter by type (user/assistant/queue-operation)
        limit: Max entries to return
        offset: Pagination offset
    """
    type_filter = "AND e.entry_type = $entryType" if entry_type else ""

    results = run_query(
        f"""
        MATCH (e:TranscriptEntry)-[:IN_TRANSCRIPT]->(ts:TranscriptSession {{id: $sessionId}})
        WHERE true {type_filter}
        RETURN e
        ORDER BY e.timestamp ASC
        SKIP $offset
        LIMIT $limit
        """,
        {"sessionId": session_id, "entryType": entry_type, "offset": offset, "limit": limit}
    )
    return [_node_to_dict(r, "e") for r in results]


def get_transcript_tool_uses(session_id: str, tool_name: Optional[str] = None) -> list[dict]:
    """
    Get all tool uses from a transcript session.

    Args:
        session_id: Transcript session ID
        tool_name: Filter by tool name (optional)
    """
    name_filter = "AND t.tool_name = $toolName" if tool_name else ""

    results = run_query(
        f"""
        MATCH (t:TranscriptToolUse)-[:TOOL_IN_ENTRY]->(e:TranscriptEntry)-[:IN_TRANSCRIPT]->(ts:TranscriptSession {{id: $sessionId}})
        WHERE true {name_filter}
        RETURN t, e.timestamp as timestamp, e.model as model
        ORDER BY e.timestamp ASC
        """,
        {"sessionId": session_id, "toolName": tool_name}
    )

    tools = []
    for r in results:
        t = _node_to_dict(r, "t")
        t["timestamp"] = str(r.get("timestamp", ""))
        t["model"] = r.get("model")
        tools.append(t)
    return tools


def get_transcript_stats(project_dir: str, days: int = 7) -> dict:
    """
    Get aggregate transcript statistics for a project.

    Args:
        project_dir: Project path
        days: Number of days to look back
    """
    duration_str = f"P{days}D"

    results = run_query(
        """
        MATCH (ts:TranscriptSession)-[:TRANSCRIPT_OF]->(s:Session)-[:IN_PROJECT]->(p:Project {path: $projectPath})
        WHERE ts.parsed_at > datetime() - duration($durationStr)
        WITH count(ts) as session_count,
             sum(ts.entry_count) as total_entries,
             sum(ts.total_input_tokens) as total_input,
             sum(ts.total_output_tokens) as total_output,
             sum(ts.total_cache_creation_tokens) as total_cache_creation,
             sum(ts.total_cache_read_tokens) as total_cache_read

        RETURN session_count, total_entries, total_input, total_output,
               total_cache_creation, total_cache_read
        """,
        {"projectPath": project_dir, "durationStr": duration_str}
    )

    if not results:
        return {
            "session_count": 0,
            "total_entries": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_creation_tokens": 0,
            "total_cache_read_tokens": 0,
            "days": days
        }

    r = results[0]
    return {
        "session_count": int(r.get("session_count") or 0),
        "total_entries": int(r.get("total_entries") or 0),
        "total_input_tokens": int(r.get("total_input") or 0),
        "total_output_tokens": int(r.get("total_output") or 0),
        "total_cache_creation_tokens": int(r.get("total_cache_creation") or 0),
        "total_cache_read_tokens": int(r.get("total_cache_read") or 0),
        "days": days
    }


def get_tool_usage_breakdown(project_dir: str, days: int = 7) -> list[dict]:
    """
    Get tool usage breakdown from transcripts.

    Returns list of {tool_name, count, avg_per_session} sorted by count.
    """
    duration_str = f"P{days}D"

    results = run_query(
        """
        MATCH (t:TranscriptToolUse)-[:TOOL_IN_ENTRY]->(e:TranscriptEntry)-[:IN_TRANSCRIPT]->(ts:TranscriptSession)
        MATCH (ts)-[:TRANSCRIPT_OF]->(s:Session)-[:IN_PROJECT]->(p:Project {path: $projectPath})
        WHERE ts.parsed_at > datetime() - duration($durationStr)
        WITH t.tool_name as tool_name, count(t) as count, count(DISTINCT ts) as session_count
        RETURN tool_name, count, toFloat(count) / session_count as avg_per_session
        ORDER BY count DESC
        """,
        {"projectPath": project_dir, "durationStr": duration_str}
    )

    return [
        {
            "tool_name": r.get("tool_name"),
            "count": int(r.get("count") or 0),
            "avg_per_session": round(float(r.get("avg_per_session") or 0), 2)
        }
        for r in results
    ]


def get_model_usage_breakdown(project_dir: str, days: int = 7) -> list[dict]:
    """
    Get model usage breakdown from transcripts.

    Returns list of {model, message_count, input_tokens, output_tokens}.
    """
    duration_str = f"P{days}D"

    results = run_query(
        """
        MATCH (e:TranscriptEntry)-[:IN_TRANSCRIPT]->(ts:TranscriptSession)
        MATCH (ts)-[:TRANSCRIPT_OF]->(s:Session)-[:IN_PROJECT]->(p:Project {path: $projectPath})
        WHERE ts.parsed_at > datetime() - duration($durationStr)
        AND e.entry_type = 'assistant'
        AND e.model IS NOT NULL
        WITH e.model as model,
             count(e) as message_count,
             sum(e.input_tokens) as input_tokens,
             sum(e.output_tokens) as output_tokens
        RETURN model, message_count, input_tokens, output_tokens
        ORDER BY message_count DESC
        """,
        {"projectPath": project_dir, "durationStr": duration_str}
    )

    return [
        {
            "model": r.get("model"),
            "message_count": int(r.get("message_count") or 0),
            "input_tokens": int(r.get("input_tokens") or 0),
            "output_tokens": int(r.get("output_tokens") or 0)
        }
        for r in results
    ]


def clear_transcript_session(session_id: str) -> int:
    """
    Clear all transcript data for a session (for re-parsing).

    Returns count of deleted entries.
    """
    # First get count
    count_result = run_query(
        """
        MATCH (e:TranscriptEntry)-[:IN_TRANSCRIPT]->(ts:TranscriptSession {id: $sessionId})
        RETURN count(e) as count
        """,
        {"sessionId": session_id}
    )
    count = int(count_result[0].get("count") or 0) if count_result else 0

    # Delete tool uses
    run_write_query(
        """
        MATCH (t:TranscriptToolUse)-[:TOOL_IN_ENTRY]->(e:TranscriptEntry)-[:IN_TRANSCRIPT]->(ts:TranscriptSession {id: $sessionId})
        DETACH DELETE t
        """,
        {"sessionId": session_id}
    )

    # Delete entries
    run_write_query(
        """
        MATCH (e:TranscriptEntry)-[:IN_TRANSCRIPT]->(ts:TranscriptSession {id: $sessionId})
        DETACH DELETE e
        """,
        {"sessionId": session_id}
    )

    # Reset aggregates
    run_write_query(
        """
        MATCH (ts:TranscriptSession {id: $sessionId})
        SET ts.entry_count = 0,
            ts.total_input_tokens = 0,
            ts.total_output_tokens = 0,
            ts.total_cache_creation_tokens = 0,
            ts.total_cache_read_tokens = 0
        """,
        {"sessionId": session_id}
    )

    return count
