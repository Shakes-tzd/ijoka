#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["neo4j>=5.0"]
# ///
"""
Ijoka Graph Database Helper

Shared module for all hooks to access Memgraph (source of truth).
Mirrors the MCP server's db.ts operations for consistency.

Architecture:
- Memgraph = Source of Truth (all writes go here)
- SQLite = Read cache for Tauri UI (synced from Memgraph)
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from neo4j import GraphDatabase, Driver
from neo4j.exceptions import ServiceUnavailable, AuthError


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


def run_write_query(cypher: str, params: Optional[dict] = None) -> list[dict]:
    """Run a write query and return results."""
    driver = get_driver()
    config = get_config()
    with driver.session(database=config["database"]) as session:
        result = session.run(cypher, params or {})
        return [dict(record) for record in result]


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
    """Get the currently active feature (status = 'in_progress'). Returns format compatible with db_helper."""
    results = run_query(
        """
        MATCH (f:Feature {status: 'in_progress'})-[:BELONGS_TO]->(p:Project {path: $projectPath})
        RETURN f
        LIMIT 1
        """,
        {"projectPath": project_dir}
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


def get_or_create_session_work_feature(project_dir: str) -> dict:
    """
    Get or create the 'Session Work' pseudo-feature for meta/management activities.
    This feature captures activities like:
    - MCP tool calls (ijoka_create_feature, ijoka_status, etc.)
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


def start_feature(feature_id: str, agent: Optional[str] = None) -> Optional[dict]:
    """Start a feature (set status to 'in_progress')."""
    results = run_write_query(
        """
        MATCH (f:Feature {id: $featureId})
        SET f.status = 'in_progress',
            f.assigned_agent = $agent,
            f.updated_at = datetime()
        RETURN f
        """,
        {"featureId": feature_id, "agent": agent}
    )
    return _node_to_dict(results[0], "f") if results else None


def complete_feature(feature_id: str) -> Optional[dict]:
    """Mark a feature as complete."""
    results = run_write_query(
        """
        MATCH (f:Feature {id: $featureId})
        SET f.status = 'complete',
            f.completed_at = datetime(),
            f.updated_at = datetime()
        RETURN f
        """,
        {"featureId": feature_id}
    )
    return _node_to_dict(results[0], "f") if results else None


def activate_feature(project_dir: str, feature_id: str) -> bool:
    """
    Activate a feature and deactivate all others in the project.
    Returns True if successful.
    """
    # Deactivate all in_progress features for this project
    run_write_query(
        """
        MATCH (f:Feature {status: 'in_progress'})-[:BELONGS_TO]->(p:Project {path: $projectPath})
        SET f.status = 'pending', f.updated_at = datetime()
        """,
        {"projectPath": project_dir}
    )
    # Activate the target feature
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
    in_progress: bool = True
) -> str:
    """Create a new feature and return its ID."""
    feature_id = str(uuid.uuid4())

    # Ensure project exists
    get_or_create_project(project_dir)

    # Deactivate other features if this one starts active
    if in_progress:
        run_write_query(
            """
            MATCH (f:Feature {status: 'in_progress'})-[:BELONGS_TO]->(p:Project {path: $projectPath})
            SET f.status = 'pending', f.updated_at = datetime()
            """,
            {"projectPath": project_dir}
        )

    status = "in_progress" if in_progress else "pending"
    run_write_query(
        """
        MATCH (p:Project {path: $projectPath})
        CREATE (f:Feature {
            id: $id,
            description: $description,
            category: $category,
            status: $status,
            priority: $priority,
            steps: $steps,
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
            "status": status,
            "priority": priority,
            "steps": steps or [],
        }
    )
    return feature_id


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
    run_write_query("""
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
    """, {
        "featureId": feature_id,
        "stepId": step_id,
        "description": description,
        "status": status,
        "order": order,
        "expectedTools": expected_tools or []
    })
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

    return _node_to_dict(results[0], "s") if results else None


def sync_steps_from_todos(feature_id: str, todos: list) -> list:
    """
    Sync Step nodes from TodoWrite payload.
    Creates new steps, updates existing, marks removed as skipped.
    Returns list of step IDs.
    """
    existing_steps = get_steps(feature_id)
    existing_by_desc = {s.get("description", ""): s for s in existing_steps}

    step_ids = []
    for i, todo in enumerate(todos):
        desc = todo.get("content", "")
        status_map = {"pending": "pending", "in_progress": "in_progress", "completed": "completed"}
        status = status_map.get(todo.get("status", "pending"), "pending")

        if desc in existing_by_desc:
            # Update existing step
            step = existing_by_desc[desc]
            update_step_status(step["id"], status)
            step_ids.append(step["id"])
        else:
            # Create new step
            step_id = create_step(feature_id, desc, i, status)
            step_ids.append(step_id)

    # Mark steps not in todos as skipped
    current_descs = {todo.get("content", "") for todo in todos}
    for step in existing_steps:
        if step.get("description", "") not in current_descs:
            update_step_status(step["id"], "skipped")

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
# DEPRECATED - Import from feature_list.json
# =============================================================================
# This function is deprecated. The graph database is now the single source of truth.
# Use ijoka_create_feature MCP tool or import from ijoka-implementation-plan.yaml instead.
# This function will be removed in a future version.

def sync_features_from_json(project_dir: str, features: list[dict]) -> None:
    """
    DEPRECATED: Import features from feature_list.json to graph database.

    WARNING: This function is deprecated and will be removed.
    The graph database is now the single source of truth.
    Use ijoka_create_feature MCP tool instead.
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
