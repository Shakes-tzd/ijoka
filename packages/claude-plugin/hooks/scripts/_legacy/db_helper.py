"""
Ijoka SQLite Database Helper

Shared module for all hooks to access the SQLite database directly.
Uses WAL mode for concurrent access from multiple processes.
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def get_db_path() -> Path:
    """Get the shared database path: ~/.ijoka/ijoka.db"""
    return Path.home() / ".ijoka" / "ijoka.db"


def get_connection() -> sqlite3.Connection:
    """
    Get a database connection configured for concurrent access.
    Uses WAL mode and 10-second timeout to handle parallel hook execution.
    """
    db_path = get_db_path()

    # Ensure directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row

    # Configure for concurrent access (same as Rust/Tauri app)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA cache_size = -2000")

    # Ensure tables exist (matches Rust schema)
    _ensure_schema(conn)

    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Ensure database tables exist (idempotent)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            source_agent TEXT NOT NULL,
            session_id TEXT NOT NULL,
            project_dir TEXT NOT NULL,
            tool_name TEXT,
            payload TEXT,
            feature_id TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS features (
            id TEXT PRIMARY KEY,
            project_dir TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT DEFAULT 'functional',
            passes INTEGER DEFAULT 0,
            in_progress INTEGER DEFAULT 0,
            agent TEXT,
            steps TEXT,
            work_count INTEGER DEFAULT 0,
            completion_criteria TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            source_agent TEXT NOT NULL,
            project_dir TEXT NOT NULL,
            started_at TEXT DEFAULT (datetime('now')),
            last_activity TEXT DEFAULT (datetime('now')),
            status TEXT DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
        CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_dir);
        CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_events_feature_id ON events(feature_id);
        CREATE INDEX IF NOT EXISTS idx_features_project ON features(project_dir);
    """)
    conn.commit()


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
    feature_id: Optional[str] = None
) -> int:
    """Insert an event and return its ID."""
    conn = get_connection()
    try:
        payload_json = json.dumps(payload) if payload else None
        cursor = conn.execute(
            """INSERT INTO events
               (event_type, source_agent, session_id, project_dir, tool_name, payload, feature_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_type, source_agent, session_id, project_dir, tool_name, payload_json, feature_id)
        )
        conn.commit()
        return cursor.lastrowid or 0
    finally:
        conn.close()


# =============================================================================
# Feature Operations
# =============================================================================

def get_features(project_dir: str) -> list[dict]:
    """Get all features for a project."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """SELECT id, project_dir, description, category, passes, in_progress,
                      agent, steps, work_count, completion_criteria, updated_at
               FROM features WHERE project_dir = ? ORDER BY id""",
            (project_dir,)
        )
        features = []
        for row in cursor:
            features.append({
                "id": row["id"],
                "project_dir": row["project_dir"],
                "description": row["description"],
                "category": row["category"],
                "passes": bool(row["passes"]),
                "inProgress": bool(row["in_progress"]),
                "agent": row["agent"],
                "steps": json.loads(row["steps"]) if row["steps"] else None,
                "workCount": row["work_count"] or 0,
                "completionCriteria": json.loads(row["completion_criteria"]) if row["completion_criteria"] else None,
                "updatedAt": row["updated_at"],
            })
        return features
    finally:
        conn.close()


def get_active_feature(project_dir: str) -> Optional[dict]:
    """Get the currently active feature (in_progress = 1)."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """SELECT id, project_dir, description, category, passes, in_progress,
                      agent, steps, work_count, completion_criteria, updated_at
               FROM features WHERE project_dir = ? AND in_progress = 1 LIMIT 1""",
            (project_dir,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "id": row["id"],
                "project_dir": row["project_dir"],
                "description": row["description"],
                "category": row["category"],
                "passes": bool(row["passes"]),
                "inProgress": bool(row["in_progress"]),
                "agent": row["agent"],
                "steps": json.loads(row["steps"]) if row["steps"] else None,
                "workCount": row["work_count"] or 0,
                "completionCriteria": json.loads(row["completion_criteria"]) if row["completion_criteria"] else None,
                "updatedAt": row["updated_at"],
            }
        return None
    finally:
        conn.close()


def sync_features_from_json(project_dir: str, features: list[dict]) -> None:
    """
    Sync features from feature_list.json to SQLite database.
    Used for backward compatibility - import JSON into SQLite.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")

        for index, feature in enumerate(features):
            feature_id = f"{project_dir}:{index}"
            steps_json = json.dumps(feature.get("steps")) if feature.get("steps") else None
            criteria_json = json.dumps(feature.get("completionCriteria")) if feature.get("completionCriteria") else None

            conn.execute(
                """INSERT OR REPLACE INTO features
                   (id, project_dir, description, category, passes, in_progress, agent, steps, work_count, completion_criteria, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (
                    feature_id,
                    project_dir,
                    feature.get("description", ""),
                    feature.get("category", "functional"),
                    1 if feature.get("passes") else 0,
                    1 if feature.get("inProgress") else 0,
                    feature.get("agent"),
                    steps_json,
                    feature.get("workCount", 0),
                    criteria_json,
                )
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_feature_status(
    feature_id: str,
    passes: Optional[bool] = None,
    in_progress: Optional[bool] = None,
    work_count: Optional[int] = None
) -> bool:
    """Update a feature's status fields. Returns True if feature was found."""
    conn = get_connection()
    try:
        updates = []
        params = []

        if passes is not None:
            updates.append("passes = ?")
            params.append(1 if passes else 0)
        if in_progress is not None:
            updates.append("in_progress = ?")
            params.append(1 if in_progress else 0)
        if work_count is not None:
            updates.append("work_count = ?")
            params.append(work_count)

        if not updates:
            return False

        updates.append("updated_at = datetime('now')")
        params.append(feature_id)

        cursor = conn.execute(
            f"UPDATE features SET {', '.join(updates)} WHERE id = ?",
            params
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def activate_feature(project_dir: str, feature_id: str) -> bool:
    """
    Activate a feature (set in_progress = 1) and deactivate all others.
    Uses a transaction to ensure atomicity.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")

        # Deactivate all features in this project
        conn.execute(
            "UPDATE features SET in_progress = 0, updated_at = datetime('now') WHERE project_dir = ?",
            (project_dir,)
        )

        # Activate the target feature
        cursor = conn.execute(
            "UPDATE features SET in_progress = 1, updated_at = datetime('now') WHERE id = ?",
            (feature_id,)
        )

        conn.commit()
        return cursor.rowcount > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def complete_feature(feature_id: str) -> bool:
    """Mark a feature as complete (passes = 1, in_progress = 0)."""
    return update_feature_status(feature_id, passes=True, in_progress=False)


def increment_work_count(feature_id: str) -> int:
    """Increment a feature's work count and return the new value."""
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")

        cursor = conn.execute(
            "UPDATE features SET work_count = work_count + 1, updated_at = datetime('now') WHERE id = ?",
            (feature_id,)
        )

        if cursor.rowcount == 0:
            conn.rollback()
            return 0

        # Get the new work count
        cursor = conn.execute("SELECT work_count FROM features WHERE id = ?", (feature_id,))
        row = cursor.fetchone()

        conn.commit()
        return row["work_count"] if row else 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_feature(
    project_dir: str,
    description: str,
    category: str = "functional",
    steps: Optional[list[str]] = None,
    completion_criteria: Optional[dict] = None,
    in_progress: bool = True
) -> str:
    """Create a new feature and return its ID."""
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")

        # Get next index for this project
        cursor = conn.execute(
            "SELECT COUNT(*) as count FROM features WHERE project_dir = ?",
            (project_dir,)
        )
        count = cursor.fetchone()["count"]
        feature_id = f"{project_dir}:{count}"

        # Deactivate other features if this one is active
        if in_progress:
            conn.execute(
                "UPDATE features SET in_progress = 0, updated_at = datetime('now') WHERE project_dir = ?",
                (project_dir,)
            )

        steps_json = json.dumps(steps) if steps else None
        criteria_json = json.dumps(completion_criteria) if completion_criteria else None

        conn.execute(
            """INSERT INTO features
               (id, project_dir, description, category, passes, in_progress, steps, work_count, completion_criteria, updated_at)
               VALUES (?, ?, ?, ?, 0, ?, ?, 0, ?, datetime('now'))""",
            (feature_id, project_dir, description, 1 if in_progress else 0, steps_json, criteria_json)
        )

        conn.commit()
        return feature_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def find_similar_feature(project_dir: str, description: str) -> Optional[dict]:
    """Find an existing feature with a similar description."""
    features = get_features(project_dir)
    desc_lower = description.lower()
    desc_words = set(desc_lower.split())

    for feature in features:
        existing_desc = feature.get("description", "").lower()

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
# Session Operations
# =============================================================================

def start_session(session_id: str, source_agent: str, project_dir: str) -> None:
    """Record a session start."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO sessions
               (session_id, source_agent, project_dir, started_at, last_activity, status)
               VALUES (?, ?, ?, datetime('now'), datetime('now'), 'active')""",
            (session_id, source_agent, project_dir)
        )
        conn.commit()
    finally:
        conn.close()


def end_session(session_id: str) -> None:
    """Mark a session as ended."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE sessions SET status = 'ended', last_activity = datetime('now') WHERE session_id = ?",
            (session_id,)
        )
        conn.commit()
    finally:
        conn.close()


def update_session_activity(session_id: str) -> None:
    """Update a session's last_activity timestamp."""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE sessions SET last_activity = datetime('now') WHERE session_id = ?",
            (session_id,)
        )
        conn.commit()
    finally:
        conn.close()


# =============================================================================
# Stats Operations
# =============================================================================

def get_stats(project_dir: Optional[str] = None) -> dict:
    """Get feature statistics."""
    conn = get_connection()
    try:
        if project_dir:
            total = conn.execute(
                "SELECT COUNT(*) FROM features WHERE project_dir = ?", (project_dir,)
            ).fetchone()[0]
            completed = conn.execute(
                "SELECT COUNT(*) FROM features WHERE project_dir = ? AND passes = 1", (project_dir,)
            ).fetchone()[0]
            in_progress = conn.execute(
                "SELECT COUNT(*) FROM features WHERE project_dir = ? AND in_progress = 1 AND passes = 0", (project_dir,)
            ).fetchone()[0]
        else:
            total = conn.execute("SELECT COUNT(*) FROM features").fetchone()[0]
            completed = conn.execute("SELECT COUNT(*) FROM features WHERE passes = 1").fetchone()[0]
            in_progress = conn.execute("SELECT COUNT(*) FROM features WHERE in_progress = 1 AND passes = 0").fetchone()[0]

        percentage = (completed / total * 100) if total > 0 else 0

        return {
            "total": total,
            "completed": completed,
            "inProgress": in_progress,
            "percentage": percentage,
        }
    finally:
        conn.close()


# =============================================================================
# Session State Cache (for feature classification)
# =============================================================================

def _ensure_session_state_table(conn: sqlite3.Connection) -> None:
    """Ensure session_state table exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_state (
            session_id TEXT PRIMARY KEY,
            active_feature_id TEXT,
            classified_at TEXT,
            classification_source TEXT,
            last_prompt TEXT
        )
    """)
    conn.commit()


def get_session_state(session_id: str) -> Optional[dict]:
    """Get cached session state (feature classification)."""
    conn = get_connection()
    try:
        _ensure_session_state_table(conn)
        cursor = conn.execute(
            """SELECT active_feature_id, classified_at, classification_source, last_prompt
               FROM session_state WHERE session_id = ?""",
            (session_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                "activeFeatureId": row["active_feature_id"],
                "classifiedAt": row["classified_at"],
                "classificationSource": row["classification_source"],
                "lastPrompt": row["last_prompt"],
            }
        return None
    finally:
        conn.close()


def set_session_state(
    session_id: str,
    active_feature_id: Optional[str],
    classification_source: str = "unknown",
    last_prompt: Optional[str] = None
) -> None:
    """Cache session state (feature classification result)."""
    conn = get_connection()
    try:
        _ensure_session_state_table(conn)
        conn.execute(
            """INSERT OR REPLACE INTO session_state
               (session_id, active_feature_id, classified_at, classification_source, last_prompt)
               VALUES (?, ?, datetime('now'), ?, ?)""",
            (session_id, active_feature_id, classification_source, last_prompt[:500] if last_prompt else None)
        )
        conn.commit()
    finally:
        conn.close()


def clear_session_state(session_id: str) -> None:
    """Clear cached session state."""
    conn = get_connection()
    try:
        _ensure_session_state_table(conn)
        conn.execute("DELETE FROM session_state WHERE session_id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()
