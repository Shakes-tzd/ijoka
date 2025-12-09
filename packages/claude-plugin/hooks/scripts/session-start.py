#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["neo4j>=5.0"]
# ///
"""
Ijoka Session Start Hook

Records session start in graph database and provides feature context to Claude.
Runs quick diagnostics to catch configuration issues early.

Architecture:
- Memgraph = Single source of truth
- MCP tools = Feature management interface
- feature_list.json = DEPRECATED (no longer used)
"""

import json
import os
import sys
from pathlib import Path

# Import shared database helper
sys.path.insert(0, str(Path(__file__).parent))
import graph_db_helper as db_helper


def run_quick_diagnostics(project_dir: str) -> list[str]:
    """Run quick diagnostic checks and return any warnings."""
    warnings = []

    try:
        # Check for unmigrated feature_list.json
        feature_list_path = Path(project_dir) / "feature_list.json"
        if feature_list_path.exists():
            warnings.append("⚠️ Unmigrated feature_list.json found. Run `/ijoka:migrate` to import features to graph DB.")

        # Ensure Session Work feature exists
        results = db_helper.run_query("""
            MATCH (f:Feature {is_session_work: true})-[:BELONGS_TO]->(p:Project {path: $projectPath})
            RETURN f.status as status
        """, {"projectPath": project_dir})
        if not results:
            db_helper.get_or_create_session_work_feature(project_dir)

        # Check for relationship consistency issues
        results = db_helper.run_query("""
            MATCH (e:Event)-[r:BELONGS_TO]->(f:Feature)
            RETURN count(r) as count
        """)
        if results and results[0]['count'] > 0:
            warnings.append(f"⚠️ {results[0]['count']} events have incorrect relationships. Run `graph_validator.py --fix`")

    except Exception as e:
        warnings.append(f"⚠️ Diagnostic: {e}")

    return warnings


def output_response(context: str) -> None:
    """Output JSON response with context."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context
        }
    }))


def main():
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        hook_input = {}

    session_id = hook_input.get("session_id") or os.environ.get("CLAUDE_SESSION_ID", "unknown")
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    # Run quick diagnostics
    diagnostic_warnings = run_quick_diagnostics(project_dir)

    # Record session start in database
    db_helper.start_session(session_id, "claude-code", project_dir)

    # Record session start event
    db_helper.insert_event(
        event_type="SessionStart",
        source_agent="claude-code",
        session_id=session_id,
        project_dir=project_dir,
        payload={"action": "session_started", "diagnostics": diagnostic_warnings}
    )

    # Get features from graph database (single source of truth)
    features = db_helper.get_features(project_dir)

    if not features:
        output_response("No features found in graph database. Use ijoka_create_feature MCP tool or import from ijoka-implementation-plan.yaml.")
        return

    # Calculate stats
    total = len(features)
    completed = sum(1 for f in features if f.get("passes"))
    percentage = int(completed * 100 / total) if total > 0 else 0

    # Find active feature
    active_feature = None
    for f in features:
        if f.get("inProgress"):
            active_feature = f
            break

    # Build diagnostic section if there are warnings
    diagnostic_section = ""
    if diagnostic_warnings:
        diagnostic_section = "\n---\n\n## Diagnostics\n\n" + "\n".join(diagnostic_warnings) + "\n"

    if active_feature:
        # Active feature exists - show it with auto-completion info
        criteria_type = "manual"
        if active_feature.get("completionCriteria"):
            criteria_type = active_feature["completionCriteria"].get("type", "manual")
        work_count = active_feature.get("workCount", 0)

        context = f"""## Active Feature

**Currently Working On:** {active_feature['description']}

**Progress:** {completed}/{total} features complete ({percentage}%)

**Auto-Completion:** {criteria_type} | Work count: {work_count}

All tool calls will be linked to this feature. Features auto-complete when criteria are met (build passes, tests pass, or work count threshold reached).

---

**Switching features:** The system auto-detects when you're working on a different feature and switches automatically based on AI classification.
{diagnostic_section}"""
        output_response(context)
    else:
        # No active feature - show summary
        feature_lines = []
        for i, f in enumerate(features[:10]):
            status = "x" if f.get("passes") else " "
            desc = f.get("description", "")[:60]
            feature_lines.append(f"[{i}] [{status}] {desc}")

        feature_summary = "\n".join(feature_lines)

        context = f"""## No Active Feature

**Progress:** {completed}/{total} features complete ({percentage}%)

**Features:**
{feature_summary}

**Auto-Mode Active:** When you start working, the system will:
1. Auto-match your work to an existing feature (AI classification)
2. Auto-create a new feature if no match found
3. Auto-complete features when completion criteria are met

**Manual Commands (optional):**
- `/next-feature` - Manually select next feature
- `/complete-feature` - Force complete active feature
{diagnostic_section}"""
        output_response(context)


if __name__ == "__main__":
    main()
