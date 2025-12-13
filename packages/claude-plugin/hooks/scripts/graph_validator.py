#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["neo4j>=5.0"]
# ///
"""
Ijoka Graph Database Validator

Validates graph database consistency and relationship integrity.
Run on startup or on-demand to catch issues early.

Usage:
    uv run graph_validator.py [--fix]

Options:
    --fix   Automatically fix issues where possible
"""

import sys
from dataclasses import dataclass
from typing import Optional

# Import shared database helper
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import graph_db_helper as db


@dataclass
class ValidationIssue:
    """Represents a validation issue found in the graph."""
    severity: str  # 'error', 'warning', 'info'
    category: str
    message: str
    fix_query: Optional[str] = None
    fix_params: Optional[dict] = None


class GraphValidator:
    """Validates graph database consistency."""

    def __init__(self, project_path: str):
        self.project_path = project_path
        self.issues: list[ValidationIssue] = []

    def validate_all(self) -> list[ValidationIssue]:
        """Run all validation checks."""
        self.issues = []

        self._check_project_exists()
        self._check_orphaned_features()
        self._check_orphaned_events()
        self._check_event_relationship_consistency()
        self._check_session_work_feature()
        self._check_status_consistency()
        self._check_duplicate_features()

        return self.issues

    def _check_project_exists(self) -> None:
        """Verify project node exists."""
        results = db.run_query(
            "MATCH (p:Project {path: $path}) RETURN p",
            {"path": self.project_path}
        )
        if not results:
            self.issues.append(ValidationIssue(
                severity="error",
                category="project",
                message=f"Project not found: {self.project_path}",
                fix_query="""
                    CREATE (p:Project {
                        id: randomUUID(),
                        path: $path,
                        name: $name,
                        created_at: datetime(),
                        updated_at: datetime()
                    })
                """,
                fix_params={"path": self.project_path, "name": Path(self.project_path).name}
            ))

    def _check_orphaned_features(self) -> None:
        """Find features not linked to any project."""
        results = db.run_query("""
            MATCH (f:Feature)
            WHERE NOT EXISTS { MATCH (f)-[:BELONGS_TO]->(:Project) }
            RETURN f.id as id, f.description as desc
        """)
        for r in results:
            self.issues.append(ValidationIssue(
                severity="warning",
                category="feature",
                message=f"Orphaned feature (no project): {r['desc'][:50]}...",
                fix_query="""
                    MATCH (f:Feature {id: $featureId})
                    MATCH (p:Project {path: $projectPath})
                    MERGE (f)-[:BELONGS_TO]->(p)
                """,
                fix_params={"featureId": r['id'], "projectPath": self.project_path}
            ))

    def _check_orphaned_events(self) -> None:
        """Find events not linked to any session."""
        results = db.run_query("""
            MATCH (e:Event)
            WHERE NOT EXISTS { MATCH (e)-[:TRIGGERED_BY]->(:Session) }
            RETURN e.id as id, e.event_type as type, e.tool_name as tool
            LIMIT 10
        """)
        if results:
            self.issues.append(ValidationIssue(
                severity="info",
                category="event",
                message=f"Found {len(results)} events without session link"
            ))

    def _check_event_relationship_consistency(self) -> None:
        """Check that events use LINKED_TO (not BELONGS_TO) for feature relationships."""
        # Check for incorrect BELONGS_TO relationships from events to features
        results = db.run_query("""
            MATCH (e:Event)-[r:BELONGS_TO]->(f:Feature)
            RETURN count(r) as count
        """)
        count = results[0]['count'] if results else 0
        if count > 0:
            self.issues.append(ValidationIssue(
                severity="error",
                category="relationship",
                message=f"Found {count} events using BELONGS_TO instead of LINKED_TO for features",
                fix_query="""
                    MATCH (e:Event)-[r:BELONGS_TO]->(f:Feature)
                    DELETE r
                    CREATE (e)-[:LINKED_TO]->(f)
                """,
                fix_params={}
            ))

    def _check_session_work_feature(self) -> None:
        """Verify Session Work feature exists and is properly configured."""
        results = db.run_query("""
            MATCH (f:Feature {is_session_work: true})-[:BELONGS_TO]->(p:Project {path: $projectPath})
            RETURN f.id as id, f.status as status, f.description as desc
        """, {"projectPath": self.project_path})

        if not results:
            self.issues.append(ValidationIssue(
                severity="warning",
                category="session_work",
                message="Session Work feature not found - meta/management events won't be tracked",
                fix_query=None  # Will be created on demand by get_or_create_session_work_feature
            ))
        elif results[0]['status'] != 'in_progress':
            self.issues.append(ValidationIssue(
                severity="warning",
                category="session_work",
                message=f"Session Work feature has status '{results[0]['status']}' (should be 'in_progress')",
                fix_query="""
                    MATCH (f:Feature {is_session_work: true})-[:BELONGS_TO]->(p:Project {path: $projectPath})
                    SET f.status = 'in_progress'
                """,
                fix_params={"projectPath": self.project_path}
            ))

    def _check_status_consistency(self) -> None:
        """Check for features with invalid status values."""
        valid_statuses = ['pending', 'in_progress', 'blocked', 'complete']
        results = db.run_query("""
            MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $projectPath})
            WHERE NOT f.status IN $validStatuses
            RETURN f.id as id, f.status as status, f.description as desc
        """, {"projectPath": self.project_path, "validStatuses": valid_statuses})

        for r in results:
            self.issues.append(ValidationIssue(
                severity="error",
                category="status",
                message=f"Invalid status '{r['status']}' for feature: {r['desc'][:40]}...",
                fix_query="""
                    MATCH (f:Feature {id: $featureId})
                    SET f.status = 'pending'
                """,
                fix_params={"featureId": r['id']}
            ))

    def _check_duplicate_features(self) -> None:
        """Check for features with duplicate descriptions."""
        results = db.run_query("""
            MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $projectPath})
            WITH f.description as desc, collect(f.id) as ids, count(f) as cnt
            WHERE cnt > 1
            RETURN desc, ids, cnt
        """, {"projectPath": self.project_path})

        for r in results:
            self.issues.append(ValidationIssue(
                severity="warning",
                category="duplicate",
                message=f"Duplicate feature description ({r['cnt']}x): {r['desc'][:40]}..."
            ))

    def fix_issues(self) -> int:
        """Attempt to fix all fixable issues. Returns count of fixes applied."""
        fixed = 0
        for issue in self.issues:
            if issue.fix_query and issue.fix_params is not None:
                try:
                    db.run_write_query(issue.fix_query, issue.fix_params)
                    fixed += 1
                    print(f"  ✅ Fixed: {issue.message}")
                except Exception as e:
                    print(f"  ❌ Failed to fix: {issue.message} - {e}")
        return fixed


def run_validation(project_path: str, auto_fix: bool = False) -> bool:
    """
    Run validation and optionally fix issues.

    Returns True if no errors found (warnings OK).
    """
    print("=" * 60)
    print("IJOKA GRAPH DATABASE VALIDATION")
    print("=" * 60)
    print(f"\nProject: {project_path}")

    validator = GraphValidator(project_path)
    issues = validator.validate_all()

    if not issues:
        print("\n✅ No issues found - graph is healthy!")
        return True

    # Group by severity
    errors = [i for i in issues if i.severity == 'error']
    warnings = [i for i in issues if i.severity == 'warning']
    infos = [i for i in issues if i.severity == 'info']

    print(f"\nFound {len(issues)} issues:")
    print(f"  🔴 Errors: {len(errors)}")
    print(f"  🟡 Warnings: {len(warnings)}")
    print(f"  🔵 Info: {len(infos)}")

    # Print issues by category
    for issue in issues:
        icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}[issue.severity]
        fixable = " [fixable]" if issue.fix_query else ""
        print(f"\n{icon} [{issue.category}] {issue.message}{fixable}")

    # Auto-fix if requested
    if auto_fix and any(i.fix_query for i in issues):
        print("\n" + "-" * 40)
        print("Attempting to fix issues...")
        fixed = validator.fix_issues()
        print(f"\n✅ Fixed {fixed} issues")

        # Re-validate
        print("\n" + "-" * 40)
        print("Re-validating...")
        issues = validator.validate_all()
        errors = [i for i in issues if i.severity == 'error']
        if not errors:
            print("✅ All errors resolved!")
        else:
            print(f"🔴 {len(errors)} errors remain")

    return len(errors) == 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Validate Ijoka graph database")
    parser.add_argument("--fix", action="store_true", help="Automatically fix issues")
    parser.add_argument("--project", default="/Users/shakes/DevProjects/ijoka", help="Project path")
    args = parser.parse_args()

    # Check connection first
    if not db.is_connected():
        print("❌ Cannot connect to graph database")
        print("   Make sure Memgraph is running: docker compose up -d")
        sys.exit(1)

    success = run_validation(args.project, auto_fix=args.fix)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
