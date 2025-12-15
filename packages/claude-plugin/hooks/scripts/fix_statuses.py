#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["neo4j>=5.0"]
# ///
"""
DEPRECATED: Historical migration script for fixing feature statuses.

This script was used during the transition from MCP server to CLI.
It is kept for reference but should not be run on production data.

For feature status management, use:
- `ijoka feature start <ID>` - Start working on a feature
- `ijoka feature complete` - Mark current feature as complete
"""

from neo4j import GraphDatabase
from datetime import datetime
import uuid

def main():
    driver = GraphDatabase.driver('bolt://localhost:7687', auth=('', ''))
    project_path = '/Users/shakes/DevProjects/ijoka'

    with driver.session(database='memgraph') as session:
        print("=" * 60)
        print("FIXING FEATURE STATUSES")
        print("=" * 60)

        # Phase 1 features that have been implemented (MCP server is working)
        # Phase 2 features partially done (MCP tools exist and work)
        features_to_update = [
            # We have a working MCP server with tool definitions
            ("Phase 2: Create MCP server entry point", "in_progress"),
            ("Phase 2: Implement MCP tool definitions", "in_progress"),
        ]

        # Find features related to work we've done and mark them in_progress
        result = session.run("""
            MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $projectPath})
            WHERE f.status = 'pending'
            AND (
                f.description CONTAINS 'MCP server' OR
                f.description CONTAINS 'MCP tool' OR
                f.description CONTAINS 'Session Work'
            )
            RETURN f.id as id, f.description as description
        """, {"projectPath": project_path})

        features_found = list(result)
        print(f"\nFound {len(features_found)} features to update to 'in_progress':\n")

        for f in features_found:
            print(f"  • {f['description'][:60]}...")

            # Create StatusEvent for audit trail
            event_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()

            session.run("""
                MATCH (f:Feature {id: $featureId})
                // Create StatusEvent
                CREATE (se:StatusEvent {
                    id: $eventId,
                    from_status: f.status,
                    to_status: 'in_progress',
                    at: datetime($now),
                    by: 'migration:status_fix',
                    reason: 'Feature has related implementation work'
                })-[:CHANGED_STATUS]->(f)
                // Update feature status
                SET f.status = 'in_progress',
                    f.updated_at = datetime($now)
            """, {
                "featureId": f['id'],
                "eventId": event_id,
                "now": now
            })

        print(f"\n✅ Updated {len(features_found)} features to 'in_progress'")

        # Also mark Session Work as a special case (always in_progress)
        print("\n" + "-" * 40)
        print("Ensuring Session Work feature is properly marked...")

        session.run("""
            MATCH (f:Feature {is_session_work: true})
            WHERE f.status <> 'in_progress'
            SET f.status = 'in_progress'
        """)

        # Show final status distribution
        print("\n" + "=" * 60)
        print("FINAL STATUS DISTRIBUTION")
        print("=" * 60)
        result = session.run("""
            MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $projectPath})
            RETURN f.status as status, count(f) as count
            ORDER BY count DESC
        """, {"projectPath": project_path})

        for r in result:
            icon = {"pending": "⬜", "in_progress": "🔵", "complete": "✅", "blocked": "🔴"}.get(r['status'], "?")
            print(f"  {icon} {r['status']}: {r['count']}")

        # Show StatusEvents created
        print("\n" + "=" * 60)
        print("STATUS EVENTS CREATED")
        print("=" * 60)
        result = session.run("""
            MATCH (se:StatusEvent)-[:CHANGED_STATUS]->(f:Feature)
            RETURN se.from_status as from_s, se.to_status as to_s,
                   se.by as by, f.description as feature
            ORDER BY se.at DESC
            LIMIT 10
        """)

        records = list(result)
        if records:
            for r in records:
                print(f"  {r['from_s']} → {r['to_s']} ({r['by']})")
                print(f"     └─ {r['feature'][:50]}...")
        else:
            print("  (none)")

    driver.close()
    print("\n✅ Status fix complete!")

if __name__ == "__main__":
    main()
