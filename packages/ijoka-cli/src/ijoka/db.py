"""
Graph database client for Ijoka.

Provides connection to Memgraph/Neo4j for feature tracking and observability.
"""

import os
import re
import subprocess
import uuid
from contextlib import contextmanager
from datetime import datetime
from fnmatch import fnmatch
from typing import Generator, Optional

from loguru import logger
from neo4j import GraphDatabase, Driver, Session as Neo4jSession
from pydantic import BaseModel

from .models import (
    Feature,
    FeatureCategory,
    FeatureListItem,
    FeatureStatus,
    Insight,
    InsightType,
    Project,
    ProjectStats,
    Session,
    Step,
    StepStatus,
    WorkItemType,
)


class GraphDBConfig(BaseModel):
    """Database configuration."""
    uri: str = "bolt://localhost:7687"
    user: str = ""
    password: str = ""
    database: str = "memgraph"


class IjokaClient:
    """
    Client for interacting with Ijoka's graph database.

    Usage:
        client = IjokaClient()
        status = client.get_status()
        features = client.list_features(status="pending")
    """

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        project_path: Optional[str] = None,
    ):
        """
        Initialize the Ijoka client.

        Args:
            uri: Memgraph/Neo4j connection URI
            project_path: Project path (auto-detected if not provided)
        """
        self._uri = uri
        self._driver: Optional[Driver] = None
        self._project_path = project_path or self._detect_project_path()

    def _detect_project_path(self) -> str:
        """Detect project path using git root."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return os.getcwd()

    @property
    def driver(self) -> Driver:
        """Lazy-load the database driver."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(self._uri, auth=("", ""))
            logger.debug(f"Connected to graph database at {self._uri}")
        return self._driver

    @contextmanager
    def session(self, mode: str = "READ") -> Generator[Neo4jSession, None, None]:
        """Get a database session."""
        from neo4j import READ_ACCESS, WRITE_ACCESS
        access_mode = READ_ACCESS if mode == "READ" else WRITE_ACCESS
        session = self.driver.session(database="memgraph", default_access_mode=access_mode)
        try:
            yield session
        finally:
            session.close()

    def close(self) -> None:
        """Close the database connection."""
        if self._driver:
            self._driver.close()
            self._driver = None

    # =========================================================================
    # PROJECT OPERATIONS
    # =========================================================================

    def get_project(self) -> Optional[Project]:
        """Get the current project."""
        with self.session() as session:
            result = session.run(
                "MATCH (p:Project {path: $path}) RETURN p",
                path=self._project_path,
            )
            record = result.single()
            if not record:
                return None
            node = record["p"]
            return Project(
                id=node["id"],
                path=node["path"],
                name=node["name"],
                description=node.get("description"),
                created_at=self._parse_datetime(node.get("created_at")),
                updated_at=self._parse_datetime(node.get("updated_at")),
            )

    def ensure_project(self) -> Project:
        """Get or create the current project."""
        project = self.get_project()
        if project:
            return project

        project_id = str(uuid.uuid4())
        name = os.path.basename(self._project_path)

        with self.session(mode="WRITE") as session:
            result = session.run(
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
                id=project_id,
                path=self._project_path,
                name=name,
            )
            node = result.single()["p"]
            return Project(
                id=node["id"],
                path=node["path"],
                name=node["name"],
                created_at=self._parse_datetime(node.get("created_at")),
                updated_at=self._parse_datetime(node.get("updated_at")),
            )

    # =========================================================================
    # FEATURE OPERATIONS
    # =========================================================================

    def list_features(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[FeatureListItem]:
        """
        List features with optional filtering.

        Args:
            status: Filter by status (pending, in_progress, blocked, complete)
            category: Filter by category

        Returns:
            List of features sorted by priority (desc), created_at (asc)
        """
        with self.session() as session:
            result = session.run(
                """
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                RETURN f
                ORDER BY f.priority DESC, f.created_at ASC
                """,
                path=self._project_path,
            )
            features = []
            for record in result:
                node = record["f"]
                feat = FeatureListItem(
                    id=node["id"],
                    description=node["description"],
                    category=FeatureCategory(node["category"]),
                    type=WorkItemType(node.get("type", "feature")),
                    status=FeatureStatus(node["status"]),
                    priority=int(node.get("priority", 0)),
                    is_primary=bool(node.get("is_primary", False)),
                    work_count=int(node.get("work_count", 0)),
                    assigned_agent=node.get("assigned_agent"),
                )

                # Apply filters
                if status and feat.status.value != status:
                    continue
                if category and feat.category.value != category:
                    continue

                features.append(feat)

            return features

    def get_feature(self, feature_id: str) -> Optional[Feature]:
        """Get a feature by ID."""
        with self.session() as session:
            result = session.run(
                "MATCH (f:Feature {id: $id}) RETURN f",
                id=feature_id,
            )
            record = result.single()
            if not record:
                return None
            return self._node_to_feature(record["f"])

    def get_active_feature(self) -> Optional[Feature]:
        """Get the primary active feature, or first in_progress if no primary."""
        with self.session() as session:
            # First try to get the primary feature
            result = session.run(
                """
                MATCH (f:Feature {status: 'in_progress', is_primary: true})-[:BELONGS_TO]->(p:Project {path: $path})
                RETURN f
                LIMIT 1
                """,
                path=self._project_path,
            )
            record = result.single()
            if record:
                return self._node_to_feature(record["f"])

            # Fallback to any in_progress feature
            result = session.run(
                """
                MATCH (f:Feature {status: 'in_progress'})-[:BELONGS_TO]->(p:Project {path: $path})
                RETURN f
                ORDER BY f.priority DESC
                LIMIT 1
                """,
                path=self._project_path,
            )
            record = result.single()
            if not record:
                return None
            return self._node_to_feature(record["f"])

    def get_active_features(self) -> list[Feature]:
        """Get ALL currently active (in_progress) features."""
        with self.session() as session:
            result = session.run(
                """
                MATCH (f:Feature {status: 'in_progress'})-[:BELONGS_TO]->(p:Project {path: $path})
                RETURN f
                ORDER BY f.is_primary DESC, f.priority DESC
                """,
                path=self._project_path,
            )
            return [self._node_to_feature(record["f"]) for record in result]

    def set_primary_focus(self, feature_id: str) -> Feature:
        """
        Set a feature as the primary focus for event attribution.
        Clears is_primary from all other features.
        """
        with self.session(mode="WRITE") as session:
            # Clear all existing primary flags
            session.run(
                """
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WHERE f.is_primary = true
                SET f.is_primary = false
                """,
                path=self._project_path,
            )

            # Set the new primary
            result = session.run(
                """
                MATCH (f:Feature {id: $id})-[:BELONGS_TO]->(p:Project {path: $path})
                SET f.is_primary = true, f.updated_at = datetime()
                RETURN f
                """,
                path=self._project_path,
                id=feature_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Feature not found: {feature_id}")
            return self._node_to_feature(record["f"])

    def get_next_feature(self) -> Optional[Feature]:
        """Get the next available feature (highest priority pending)."""
        with self.session() as session:
            result = session.run(
                """
                MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $path})
                WHERE f.status = 'pending'
                RETURN f
                ORDER BY f.priority DESC, f.created_at ASC
                LIMIT 1
                """,
                path=self._project_path,
            )
            record = result.single()
            if not record:
                return None
            return self._node_to_feature(record["f"])

    def create_feature(
        self,
        description: str,
        category: str,
        priority: int = 50,
        steps: Optional[list[str]] = None,
        branch_hint: Optional[str] = None,
        file_patterns: Optional[list[str]] = None,
        work_item_type: str = "feature",
        parent_id: Optional[str] = None,
    ) -> Feature:
        """Create a new feature."""
        self.ensure_project()
        feature_id = str(uuid.uuid4())

        with self.session(mode="WRITE") as session:
            result = session.run(
                """
                MATCH (p:Project {path: $path})
                CREATE (f:Feature {
                    id: $id,
                    description: $description,
                    category: $category,
                    type: $type,
                    status: 'pending',
                    priority: $priority,
                    steps: $steps,
                    branch_hint: $branch_hint,
                    file_patterns: $file_patterns,
                    work_count: 0,
                    parent_id: $parent_id,
                    created_at: datetime(),
                    updated_at: datetime()
                })-[:BELONGS_TO]->(p)
                RETURN f
                """,
                path=self._project_path,
                id=feature_id,
                description=description,
                category=category,
                type=work_item_type,
                priority=priority,
                steps=steps or [],
                branch_hint=branch_hint,
                file_patterns=file_patterns or [],
                parent_id=parent_id,
            )

            # Create CHILD_OF relationship if parent specified
            if parent_id:
                session.run(
                    """
                    MATCH (child:Feature {id: $child_id})
                    MATCH (parent:Feature {id: $parent_id})
                    CREATE (child)-[:CHILD_OF]->(parent)
                    """,
                    child_id=feature_id,
                    parent_id=parent_id,
                )

            return self._node_to_feature(result.single()["f"])

    def start_feature(
        self,
        feature_id: Optional[str] = None,
        agent: str = "cli",
    ) -> Feature:
        """
        Start working on a feature.

        Args:
            feature_id: Feature ID (uses next available if not specified)
            agent: Agent identifier

        Returns:
            The started feature
        """
        if not feature_id:
            next_feat = self.get_next_feature()
            if not next_feat:
                raise ValueError("No pending features available")
            feature_id = next_feat.id

        session_id = f"cli-{int(datetime.now().timestamp())}"

        with self.session(mode="WRITE") as session:
            result = session.run(
                """
                MATCH (f:Feature {id: $id})
                SET f.status = 'in_progress',
                    f.assigned_agent = $agent,
                    f.claiming_session_id = $session_id,
                    f.claiming_agent = $agent,
                    f.claimed_at = datetime(),
                    f.updated_at = datetime()
                RETURN f
                """,
                id=feature_id,
                agent=agent,
                session_id=session_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Feature not found: {feature_id}")
            return self._node_to_feature(record["f"])

    def complete_feature(
        self,
        feature_id: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> Feature:
        """
        Mark a feature as complete.

        Args:
            feature_id: Feature ID (uses active feature if not specified)
            summary: Completion summary

        Returns:
            The completed feature
        """
        if not feature_id:
            active = self.get_active_feature()
            if not active:
                raise ValueError("No active feature to complete")
            feature_id = active.id

        with self.session(mode="WRITE") as session:
            result = session.run(
                """
                MATCH (f:Feature {id: $id})
                SET f.status = 'complete',
                    f.completed_at = datetime(),
                    f.updated_at = datetime(),
                    f.claiming_session_id = null,
                    f.claiming_agent = null,
                    f.claimed_at = null
                RETURN f
                """,
                id=feature_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Feature not found: {feature_id}")
            return self._node_to_feature(record["f"])

    def block_feature(
        self,
        feature_id: str,
        reason: str,
        blocking_feature_id: Optional[str] = None,
    ) -> Feature:
        """Mark a feature as blocked."""
        with self.session(mode="WRITE") as session:
            result = session.run(
                """
                MATCH (f:Feature {id: $id})
                SET f.status = 'blocked',
                    f.block_reason = $reason,
                    f.updated_at = datetime()
                RETURN f
                """,
                id=feature_id,
                reason=reason,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Feature not found: {feature_id}")

            # Create blocking relationship if specified
            if blocking_feature_id:
                session.run(
                    """
                    MATCH (f:Feature {id: $id})
                    MATCH (blocker:Feature {id: $blocker_id})
                    MERGE (f)-[:DEPENDS_ON {dependency_type: 'blocks'}]->(blocker)
                    """,
                    id=feature_id,
                    blocker_id=blocking_feature_id,
                )

            return self._node_to_feature(record["f"])

    def archive_feature(self, feature_id: str, reason: Optional[str] = None) -> bool:
        """Archive (delete) a feature."""
        with self.session(mode="WRITE") as session:
            # Delete related steps first
            session.run(
                "MATCH (s:Step)-[:BELONGS_TO]->(f:Feature {id: $id}) DETACH DELETE s",
                id=feature_id,
            )
            # Delete the feature
            result = session.run(
                "MATCH (f:Feature {id: $id}) DETACH DELETE f RETURN count(f) as deleted",
                id=feature_id,
            )
            record = result.single()
            return record and record["deleted"] > 0

    def update_feature(
        self,
        feature_id: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> Feature:
        """Update a feature's properties."""
        updates = []
        params = {"id": feature_id}

        if description is not None:
            updates.append("f.description = $description")
            params["description"] = description
        if category is not None:
            updates.append("f.category = $category")
            params["category"] = category
        if priority is not None:
            updates.append("f.priority = $priority")
            params["priority"] = priority

        if not updates:
            feat = self.get_feature(feature_id)
            if not feat:
                raise ValueError(f"Feature not found: {feature_id}")
            return feat

        updates.append("f.updated_at = datetime()")

        with self.session(mode="WRITE") as session:
            result = session.run(
                f"MATCH (f:Feature {{id: $id}}) SET {', '.join(updates)} RETURN f",
                **params,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Feature not found: {feature_id}")
            return self._node_to_feature(record["f"])

    # =========================================================================
    # HIERARCHY OPERATIONS
    # =========================================================================

    def get_children(self, feature_id: str) -> list[Feature]:
        """Get immediate children of a feature."""
        with self.session() as session:
            result = session.run(
                """
                MATCH (child:Feature)-[:CHILD_OF]->(parent:Feature {id: $id})
                RETURN child
                ORDER BY child.priority DESC, child.created_at DESC
                """,
                id=feature_id,
            )
            return [self._node_to_feature(record["child"]) for record in result]

    def get_descendants(self, feature_id: str) -> list[Feature]:
        """Get all descendants (children, grandchildren, etc.) of a feature."""
        with self.session() as session:
            result = session.run(
                """
                MATCH (descendant:Feature)-[:CHILD_OF*]->(ancestor:Feature {id: $id})
                RETURN descendant
                ORDER BY descendant.priority DESC
                """,
                id=feature_id,
            )
            return [self._node_to_feature(record["descendant"]) for record in result]

    def get_ancestors(self, feature_id: str) -> list[Feature]:
        """Get all ancestors (parent, grandparent, etc.) of a feature."""
        with self.session() as session:
            result = session.run(
                """
                MATCH (child:Feature {id: $id})-[:CHILD_OF*]->(ancestor:Feature)
                RETURN ancestor
                """,
                id=feature_id,
            )
            return [self._node_to_feature(record["ancestor"]) for record in result]

    def get_hierarchy(self, feature_id: str) -> dict:
        """
        Get full hierarchy tree rooted at feature.
        Returns dict with feature and nested children.
        """
        feature = self.get_feature(feature_id)
        if not feature:
            return {}

        children = self.get_children(feature_id)

        return {
            "feature": feature,
            "children": [self.get_hierarchy(child.id) for child in children],
            "child_count": len(children),
            "descendant_count": len(self.get_descendants(feature_id)),
        }

    def link_to_parent(self, feature_id: str, parent_id: str) -> Feature:
        """Link feature to parent (creates CHILD_OF edge)."""
        if feature_id == parent_id:
            raise ValueError("Feature cannot be its own parent")

        with self.session(mode="WRITE") as session:
            # Check for circular dependency
            ancestors = self.get_ancestors(parent_id)
            if any(a.id == feature_id for a in ancestors):
                raise ValueError("Circular dependency: feature is already an ancestor of proposed parent")

            result = session.run(
                """
                MATCH (child:Feature {id: $child_id})
                MATCH (parent:Feature {id: $parent_id})
                OPTIONAL MATCH (child)-[old:CHILD_OF]->(:Feature)
                DELETE old
                CREATE (child)-[:CHILD_OF]->(parent)
                SET child.parent_id = $parent_id
                RETURN child
                """,
                child_id=feature_id,
                parent_id=parent_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Feature or parent not found")
            return self._node_to_feature(record["child"])

    def unlink_from_parent(self, feature_id: str) -> Feature:
        """Remove CHILD_OF relationship."""
        with self.session(mode="WRITE") as session:
            result = session.run(
                """
                MATCH (child:Feature {id: $id})
                OPTIONAL MATCH (child)-[r:CHILD_OF]->(:Feature)
                DELETE r
                SET child.parent_id = null
                RETURN child
                """,
                id=feature_id,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Feature not found: {feature_id}")
            return self._node_to_feature(record["child"])

    def get_descendant_events(self, feature_id: str, limit: int = 50) -> list[dict]:
        """
        Get events linked to feature AND all its descendants.
        For aggregated event display on parent features.
        """
        with self.session() as session:
            result = session.run(
                """
                MATCH (f:Feature {id: $id})
                OPTIONAL MATCH (descendant:Feature)-[:CHILD_OF*0..]->(f)
                WITH collect(DISTINCT f) + collect(DISTINCT descendant) as features
                UNWIND features as feature
                MATCH (e:Event)-[:LINKED_TO]->(feature)
                RETURN e, feature.id as feature_id
                ORDER BY e.timestamp DESC
                LIMIT $limit
                """,
                id=feature_id,
                limit=limit,
            )
            return [
                {**dict(record["e"]), "feature_id": record["feature_id"]}
                for record in result
            ]

    # =========================================================================
    # STATS OPERATIONS
    # =========================================================================

    def get_stats(self) -> ProjectStats:
        """Get project statistics."""
        with self.session() as session:
            result = session.run(
                """
                MATCH (p:Project {path: $path})
                OPTIONAL MATCH (f:Feature)-[:BELONGS_TO]->(p)
                WITH p,
                     count(f) as total,
                     sum(CASE WHEN f.status = 'pending' THEN 1 ELSE 0 END) as pending,
                     sum(CASE WHEN f.status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                     sum(CASE WHEN f.status = 'blocked' THEN 1 ELSE 0 END) as blocked,
                     sum(CASE WHEN f.status = 'complete' THEN 1 ELSE 0 END) as complete
                RETURN total, pending, in_progress, blocked, complete
                """,
                path=self._project_path,
            )
            record = result.single()
            if not record:
                return ProjectStats()

            total = int(record["total"] or 0)
            complete = int(record["complete"] or 0)
            return ProjectStats(
                total=total,
                pending=int(record["pending"] or 0),
                in_progress=int(record["in_progress"] or 0),
                blocked=int(record["blocked"] or 0),
                complete=complete,
                completion_percentage=round((complete / total) * 100) if total > 0 else 0,
            )

    # =========================================================================
    # INSIGHT OPERATIONS
    # =========================================================================

    def record_insight(
        self,
        description: str,
        pattern_type: str,
        tags: Optional[list[str]] = None,
        feature_id: Optional[str] = None,
    ) -> Insight:
        """Record a new insight."""
        insight_id = str(uuid.uuid4())

        with self.session(mode="WRITE") as session:
            result = session.run(
                """
                CREATE (i:Insight {
                    id: $id,
                    description: $description,
                    pattern_type: $pattern_type,
                    tags: $tags,
                    usage_count: 0,
                    created_at: datetime()
                })
                RETURN i
                """,
                id=insight_id,
                description=description,
                pattern_type=pattern_type,
                tags=tags or [],
            )
            node = result.single()["i"]

            # Link to feature if provided
            if feature_id:
                session.run(
                    """
                    MATCH (i:Insight {id: $insight_id})
                    MATCH (f:Feature {id: $feature_id})
                    MERGE (i)-[:LEARNED_FROM]->(f)
                    """,
                    insight_id=insight_id,
                    feature_id=feature_id,
                )

            return Insight(
                id=node["id"],
                description=node["description"],
                pattern_type=InsightType(node["pattern_type"]),
                tags=list(node.get("tags", [])),
                usage_count=0,
                created_at=self._parse_datetime(node.get("created_at")),
            )

    def list_insights(
        self,
        query: Optional[str] = None,
        tags: Optional[list[str]] = None,
        limit: int = 10,
    ) -> list[Insight]:
        """List insights with optional filtering."""
        with self.session() as session:
            if query:
                result = session.run(
                    """
                    MATCH (i:Insight)
                    WHERE i.description CONTAINS $query
                    RETURN i
                    ORDER BY i.usage_count DESC, i.created_at DESC
                    LIMIT $limit
                    """,
                    query=query,
                    limit=limit,
                )
            elif tags:
                result = session.run(
                    """
                    MATCH (i:Insight)
                    WHERE any(tag IN $tags WHERE tag IN i.tags)
                    RETURN i
                    ORDER BY i.usage_count DESC, i.created_at DESC
                    LIMIT $limit
                    """,
                    tags=tags,
                    limit=limit,
                )
            else:
                result = session.run(
                    """
                    MATCH (i:Insight)
                    RETURN i
                    ORDER BY i.usage_count DESC, i.created_at DESC
                    LIMIT $limit
                    """,
                    limit=limit,
                )

            insights = []
            for record in result:
                node = record["i"]
                insights.append(Insight(
                    id=node["id"],
                    description=node["description"],
                    pattern_type=InsightType(node["pattern_type"]),
                    tags=list(node.get("tags", [])),
                    usage_count=int(node.get("usage_count", 0)),
                    created_at=self._parse_datetime(node.get("created_at")),
                ))
            return insights

    # =========================================================================
    # SESSION OPERATIONS
    # =========================================================================

    def get_active_session(self) -> Optional[Session]:
        """Get the active session for this project."""
        with self.session() as db_session:
            result = db_session.run(
                """
                MATCH (s:Session {status: 'active'})-[:IN_PROJECT]->(p:Project {path: $path})
                RETURN s
                ORDER BY s.last_activity DESC
                LIMIT 1
                """,
                path=self._project_path,
            )
            record = result.single()
            if not record:
                return None
            node = record["s"]
            return Session(
                id=node["id"],
                agent=node["agent"],
                status=node["status"],
                started_at=self._parse_datetime(node.get("started_at")),
                last_activity=self._parse_datetime(node.get("last_activity")),
                event_count=int(node.get("event_count", 0)),
                is_subagent=bool(node.get("is_subagent", False)),
            )

    # =========================================================================
    # PLAN OPERATIONS
    # =========================================================================

    def set_plan(self, feature_id: str, steps: list[str]) -> list[Step]:
        """
        Create Step nodes for a feature.

        Args:
            feature_id: Feature ID
            steps: List of step descriptions

        Returns:
            List of created Step models
        """
        with self.session(mode="WRITE") as session:
            # Delete existing steps first
            session.run(
                "MATCH (s:Step)-[:BELONGS_TO]->(f:Feature {id: $id}) DETACH DELETE s",
                id=feature_id,
            )

            # Create new steps
            created_steps = []
            for idx, description in enumerate(steps):
                step_id = str(uuid.uuid4())
                result = session.run(
                    """
                    MATCH (f:Feature {id: $feature_id})
                    CREATE (s:Step {
                        id: $id,
                        feature_id: $feature_id,
                        description: $description,
                        status: 'pending',
                        step_order: $step_order,
                        created_at: datetime(),
                        updated_at: datetime()
                    })-[:BELONGS_TO]->(f)
                    RETURN s
                    """,
                    id=step_id,
                    feature_id=feature_id,
                    description=description,
                    step_order=idx,
                )
                node = result.single()["s"]
                created_steps.append(Step(
                    id=node["id"],
                    feature_id=node["feature_id"],
                    description=node["description"],
                    status=StepStatus(node["status"]),
                    step_order=int(node["step_order"]),
                    created_at=self._parse_datetime(node.get("created_at")),
                    updated_at=self._parse_datetime(node.get("updated_at")),
                ))

            return created_steps

    def get_plan(self, feature_id: Optional[str] = None) -> dict:
        """
        Get plan steps with progress.

        Args:
            feature_id: Feature ID (uses active feature if not provided)

        Returns:
            Dict with: feature_id, steps, active_step, progress
        """
        if not feature_id:
            active_feature = self.get_active_feature()
            if not active_feature:
                raise ValueError("No active feature to get plan for")
            feature_id = active_feature.id

        with self.session() as session:
            result = session.run(
                """
                MATCH (s:Step)-[:BELONGS_TO]->(f:Feature {id: $id})
                RETURN s
                ORDER BY s.step_order ASC
                """,
                id=feature_id,
            )

            steps = []
            active_step = None
            completed_count = 0

            for record in result:
                node = record["s"]
                step = Step(
                    id=node["id"],
                    feature_id=feature_id,  # Use param, not node (relationship-derived)
                    description=node["description"],
                    status=StepStatus(node["status"]),
                    step_order=int(node["step_order"]),
                    created_at=self._parse_datetime(node.get("created_at")),
                    updated_at=self._parse_datetime(node.get("updated_at")),
                    completed_at=self._parse_datetime(node.get("completed_at")),
                )
                steps.append(step)

                if step.status == StepStatus.IN_PROGRESS:
                    active_step = step
                elif step.status == StepStatus.COMPLETED:
                    completed_count += 1

            total = len(steps)
            percentage = round((completed_count / total) * 100) if total > 0 else 0

            return {
                "feature_id": feature_id,
                "steps": steps,
                "active_step": active_step,
                "progress": {
                    "completed": completed_count,
                    "total": total,
                    "percentage": percentage,
                }
            }

    def get_active_step(self, feature_id: str) -> Optional[Step]:
        """
        Get the in_progress step for a feature.

        Args:
            feature_id: Feature ID

        Returns:
            The active step or None
        """
        with self.session() as session:
            result = session.run(
                """
                MATCH (s:Step {status: 'in_progress'})-[:BELONGS_TO]->(f:Feature {id: $id})
                RETURN s
                LIMIT 1
                """,
                id=feature_id,
            )
            record = result.single()
            if not record:
                return None

            node = record["s"]
            return Step(
                id=node["id"],
                feature_id=feature_id,  # Use param, not node (relationship-derived)
                description=node["description"],
                status=StepStatus(node["status"]),
                step_order=int(node["step_order"]),
                created_at=self._parse_datetime(node.get("created_at")),
                updated_at=self._parse_datetime(node.get("updated_at")),
                completed_at=self._parse_datetime(node.get("completed_at")),
            )

    def update_step_status(self, step_id: str, status: str) -> Step:
        """
        Update a step's status.

        Args:
            step_id: Step ID
            status: New status (pending, in_progress, complete)

        Returns:
            Updated Step
        """
        with self.session(mode="WRITE") as session:
            # Build SET clause based on status
            set_clause = "s.status = $status, s.updated_at = datetime()"
            if status in ("complete", "completed"):
                set_clause += ", s.completed_at = datetime()"

            result = session.run(
                f"""
                MATCH (s:Step {{id: $id}})
                OPTIONAL MATCH (s)-[:BELONGS_TO]->(f:Feature)
                SET {set_clause}
                RETURN s, f.id as feature_id
                """,
                id=step_id,
                status=status,
            )
            record = result.single()
            if not record:
                raise ValueError(f"Step not found: {step_id}")

            node = record["s"]
            # Get feature_id from relationship or node property
            feature_id = record.get("feature_id") or node.get("feature_id") or ""
            return Step(
                id=node["id"],
                feature_id=feature_id,
                description=node["description"],
                status=StepStatus(node["status"]),
                step_order=int(node.get("step_order", 0)),
                created_at=self._parse_datetime(node.get("created_at")),
                updated_at=self._parse_datetime(node.get("updated_at")),
                completed_at=self._parse_datetime(node.get("completed_at")),
            )

    def checkpoint(
        self,
        feature_id: Optional[str] = None,
        step_completed: Optional[str] = None,
        current_activity: Optional[str] = None,
    ) -> dict:
        """
        Report progress with drift detection.

        Args:
            feature_id: Feature ID (uses active feature if not provided)
            step_completed: Step description that was completed
            current_activity: What the agent is currently working on

        Returns:
            Dict with warnings list if drift detected
        """
        warnings = []

        if feature_id:
            active_feature = self.get_feature(feature_id)
        else:
            active_feature = self.get_active_feature()

        if not active_feature:
            warnings.append("No active feature - checkpoint ignored")
            return {"warnings": warnings}

        active_step = self.get_active_step(active_feature.id)

        # Handle step completion
        if step_completed and active_step:
            # Simple matching: check if step_completed is in active step description
            if step_completed.lower() in active_step.description.lower():
                # Mark current step complete
                self.update_step_status(active_step.id, "complete")

                # Start next step if available
                plan = self.get_plan(active_feature.id)
                next_pending = next(
                    (s for s in plan["steps"] if s.status == StepStatus.PENDING),
                    None
                )
                if next_pending:
                    self.update_step_status(next_pending.id, "in_progress")

        # Simple drift detection
        if current_activity and active_step:
            # Extract keywords from both (simple word-based overlap check)
            activity_words = set(current_activity.lower().split())
            step_words = set(active_step.description.lower().split())

            # Remove common words
            common_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for"}
            activity_words -= common_words
            step_words -= common_words

            # Check for overlap
            overlap = activity_words & step_words
            if not overlap and len(activity_words) > 0 and len(step_words) > 0:
                warnings.append(
                    f"Potential drift: working on '{current_activity}' "
                    f"but active step is '{active_step.description}'"
                )

        return {"warnings": warnings}

    def discover_feature(
        self,
        description: str,
        category: str,
        priority: int = 50,
        steps: Optional[list[str]] = None,
        lookback_minutes: int = 60,
        mark_complete: bool = False,
        work_item_type: str = "feature",
    ) -> dict:
        """
        Create and activate a feature (optionally marking complete immediately).

        Args:
            description: Feature description
            category: Feature category
            priority: Priority (default 50)
            steps: List of step descriptions
            lookback_minutes: How far back to look for events to reattribute (future use)
            mark_complete: If True, complete feature immediately instead of starting it

        Returns:
            Dict with feature and stats (reattributed_count currently always 0)
        """
        # Create the feature
        feature = self.create_feature(
            description=description,
            category=category,
            priority=priority,
            steps=steps or [],
            work_item_type=work_item_type,
        )

        # Create plan steps if provided
        if steps:
            self.set_plan(feature.id, steps)

        # Either complete or start the feature
        if mark_complete:
            feature = self.complete_feature(feature.id)
        else:
            feature = self.start_feature(feature.id)
            # If we have steps and we started the feature, activate first step
            if steps:
                plan = self.get_plan(feature.id)
                if plan["steps"]:
                    self.update_step_status(plan["steps"][0].id, "in_progress")

        return {
            "feature": feature,
            "reattributed_count": 0,  # Placeholder for future implementation
        }

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _node_to_feature(self, node) -> Feature:
        """Convert a neo4j node to a Feature model."""
        return Feature(
            id=node["id"],
            description=node["description"],
            category=FeatureCategory(node["category"]),
            type=WorkItemType(node.get("type", "feature")),
            status=FeatureStatus(node["status"]),
            priority=int(node.get("priority", 0)),
            is_primary=bool(node.get("is_primary", False)),
            steps=list(node.get("steps", [])),
            work_count=int(node.get("work_count", 0)),
            assigned_agent=node.get("assigned_agent"),
            claiming_session_id=node.get("claiming_session_id"),
            claiming_agent=node.get("claiming_agent"),
            claimed_at=self._parse_datetime(node.get("claimed_at")),
            block_reason=node.get("block_reason"),
            parent_id=node.get("parent_id"),
            branch_hint=node.get("branch_hint"),
            file_patterns=list(node.get("file_patterns", [])),
            created_at=self._parse_datetime(node.get("created_at")),
            updated_at=self._parse_datetime(node.get("updated_at")),
            completed_at=self._parse_datetime(node.get("completed_at")),
        )

    def _parse_datetime(self, value) -> Optional[datetime]:
        """Parse datetime from neo4j."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if hasattr(value, "to_native"):
            return value.to_native()
        return None


# =============================================================================
# ATTRIBUTION SCORING
# =============================================================================

# Type priority weights for attribution (higher = more likely to get events)
TYPE_PRIORITY = {
    "hotfix": 1.0,   # Urgent - always gets attribution
    "bug": 0.8,      # Important fixes
    "feature": 0.6,  # Standard development
    "spike": 0.4,    # Research - less likely to have specific files
    "chore": 0.3,    # Maintenance
    "epic": 0.2,     # Container - usually delegates to children
}


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text for matching."""
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


def score_attribution(
    features: list[Feature],
    file_path: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_input: Optional[dict] = None,
) -> tuple[Optional[Feature], float, str]:
    """
    Score features to determine which should receive event attribution.

    Uses a weighted scoring system:
    - File pattern match: 0.4 weight
    - Keyword overlap: 0.3 weight
    - Type priority: 0.2 weight
    - is_primary bonus: 0.1

    Args:
        features: List of active features to score
        file_path: File being edited (if applicable)
        tool_name: Tool being used
        tool_input: Tool input parameters

    Returns:
        (best_feature, score, reason) or (None, 0, "no_match")
    """
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

    activity_keywords = _extract_keywords(activity_text)

    best_feature = None
    best_score = 0.0
    best_reason = "no_match"

    for feature in features:
        score = 0.0
        reasons = []

        # 1. File pattern matching (0.4 weight)
        if file_path and feature.file_patterns:
            for pattern in feature.file_patterns:
                if fnmatch(file_path, pattern) or pattern in file_path:
                    score += 0.4
                    reasons.append(f"pattern:{pattern}")
                    break

        # 2. Keyword overlap (0.3 weight)
        feature_keywords = _extract_keywords(feature.description)
        if feature_keywords and activity_keywords:
            overlap = len(feature_keywords & activity_keywords)
            total = max(len(feature_keywords), 1)
            keyword_score = min(overlap / total, 1.0) * 0.3
            if keyword_score > 0:
                score += keyword_score
                reasons.append(f"keywords:{overlap}/{total}")

        # 3. Type priority (0.2 weight)
        type_weight = TYPE_PRIORITY.get(feature.type.value, 0.5)
        score += type_weight * 0.2

        # 4. Primary bonus (0.1)
        if feature.is_primary:
            score += 0.1
            reasons.append("primary")

        if score > best_score:
            best_score = score
            best_feature = feature
            best_reason = "; ".join(reasons) if reasons else f"type:{feature.type.value}"

    # Require minimum score threshold
    if best_score < 0.15:
        return None, best_score, "below_threshold"

    return best_feature, best_score, best_reason


# Convenience function for quick access
def get_client(project_path: Optional[str] = None) -> IjokaClient:
    """Get an Ijoka client instance."""
    uri = os.environ.get("IJOKA_DB_URI", "bolt://localhost:7687")
    return IjokaClient(uri=uri, project_path=project_path)
