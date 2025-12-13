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
- ijoka CLI/API = Feature management interface
- feature_list.json = DEPRECATED (no longer used)
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Import shared helpers
sys.path.insert(0, str(Path(__file__).parent))
import graph_db_helper as db_helper
from git_utils import resolve_project_path

# CLI/API enforcement notice - included in all session contexts
# CRITICAL: This must appear FIRST in context to ensure Claude sees it before taking action
CLI_API_ENFORCEMENT = """## ⚠️ CRITICAL: Use Ijoka CLI/API - Read This First

### FIRST ACTION: Run `ijoka status`

Before doing ANYTHING else, run the ijoka CLI to get project state:

```bash
ijoka status
```

Or use the REST API: `GET http://localhost:8000/status`

---

### Available CLI Commands

| Command | Purpose |
|---------|---------|
| `ijoka status` | **START HERE** - Get project status and active features |
| `ijoka feature list` | List all features with their status |
| `ijoka feature start [ID]` | Begin working on a feature |
| `ijoka feature complete` | Mark current feature as complete |
| `ijoka feature create` | Create a new feature |
| `ijoka plan set` / `ijoka plan show` | Plan management |
| `ijoka checkpoint` | Report progress |
| `ijoka insight record` / `ijoka insight list` | Learning capture |
| `ijoka analytics digest` | Get daily insights digest |
| `ijoka analytics ask "question"` | Natural language analytics query |

Add `--json` to any command for JSON output.

---

### REST API Endpoints (http://localhost:8000)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/status` | Project status |
| GET | `/features` | List features |
| POST | `/features` | Create feature |
| POST | `/features/{id}/start` | Start feature |
| POST | `/features/{id}/complete` | Complete feature |
| GET/POST | `/plan` | Plan management |
| POST | `/checkpoint` | Report progress |
| GET | `/analytics/digest` | Daily digest |
| POST | `/analytics/query` | Natural language query |

---

### Why CLI/API?

**NEVER bypass the CLI/API** by calling Python scripts or database queries directly.

1. **Validation** - CLI/API validates inputs and handles errors gracefully
2. **Audit Trail** - All operations are logged for debugging and analysis
3. **DRY Architecture** - Single source of truth via IjokaClient
4. **Analytics** - Full analytics and insights system available

The CLI provides the same operations as the Python scripts but with proper validation and error handling."""


def get_head_commit(project_dir: str) -> Optional[str]:
    """Get current HEAD commit hash (short form)."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            capture_output=True,
            text=True,
            cwd=project_dir,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()[:7]
    except Exception as e:
        # Silently fail - not in a git repo or git not available
        pass
    return None


def link_to_previous_session(session_id: str, project_id: str) -> Optional[str]:
    """Link this session to its predecessor if one exists."""
    try:
        prev = db_helper.get_previous_session(project_id, session_id)
        if prev:
            db_helper.link_session_ancestry(session_id, prev["id"])
            return prev["id"]
    except Exception as e:
        # Silently fail - not critical
        pass
    return None


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


def get_previous_session_summary(current_session_id: str, project_dir: str) -> Optional[str]:
    """Get summary of what the previous session accomplished."""
    try:
        # Link to previous session (already done by link_to_previous_session)
        # Query for previous session
        cypher = '''
        MATCH (current:Session {id: $current_id})-[:CONTINUED_FROM]->(prev:Session)
        OPTIONAL MATCH (prev)-[:MADE_COMMITS]->(c:Commit)
        WITH prev, collect(DISTINCT c.message) as commits, collect(DISTINCT c.hash) as hashes
        RETURN prev.started_at as started_at,
               prev.event_count as event_count,
               commits, hashes
        '''
        results = db_helper.run_query(cypher, {"current_id": current_session_id})

        if not results:
            return None

        r = results[0]
        commits = r.get("commits") or []
        hashes = r.get("hashes") or []
        event_count = int(r.get("event_count") or 0)

        if not commits and event_count == 0:
            return None

        # Format as markdown
        lines = ["## Previous Session Summary"]

        if commits:
            lines.append(f"**Commits:** {len(commits)} commit(s)")
            for msg, hash_val in zip(commits[:3], hashes[:3]):
                short_hash = str(hash_val)[:7] if hash_val else "?"
                lines.append(f"- `{short_hash}` {msg[:60]}")

        if event_count > 0:
            lines.append(f"**Activity:** {event_count} event(s)")

        return "\n".join(lines)

    except Exception:
        return None


def get_step_progress(feature_id: str) -> Optional[str]:
    """Get current plan step progress with icons."""
    try:
        steps = db_helper.get_steps(feature_id)

        if not steps:
            return None

        # Count by status
        completed = sum(1 for s in steps if s.get("status") == "completed")
        in_progress = sum(1 for s in steps if s.get("status") == "in_progress")
        pending = sum(1 for s in steps if s.get("status") == "pending")
        total = len(steps)

        percentage = int(completed * 100 / total) if total > 0 else 0

        # Format as markdown
        lines = ["## Plan Progress"]
        lines.append(f"**Progress:** {completed}/{total} steps ({percentage}%)")

        # Show steps with icons
        for step in steps[:8]:  # Limit to 8 for readability
            status = step.get("status", "pending")
            desc = step.get("description", "")[:60]

            if status == "completed":
                icon = "✅"
            elif status == "in_progress":
                icon = "⏳"
            elif status == "skipped":
                icon = "⊘"
            else:
                icon = "⭕"

            lines.append(f"{icon} {desc}")

        return "\n".join(lines)

    except Exception:
        return None


def get_recent_feature_commits(feature_id: str) -> Optional[str]:
    """Get recent commits for the active feature."""
    try:
        commits = db_helper.get_feature_commits(feature_id, limit=3)

        if not commits:
            return None

        # Format as markdown
        lines = ["## Recent Commits"]

        for commit in commits:
            hash_val = commit.get("hash", "")[:7]
            message = commit.get("message", "")[:60]
            lines.append(f"- `{hash_val}` {message}")

        return "\n".join(lines)

    except Exception:
        return None


def get_planning_context_summary(project_dir: str) -> Optional[str]:
    """Get low-context summary of planning and meta work.

    Shows counts and recent titles without loading full content.
    This gives Claude awareness that planning work exists without context bloat.
    """
    try:
        # Query for planning and meta features (completed and in-progress)
        cypher = '''
        MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $project_path})
        WHERE f.category IN ['planning', 'meta']
        WITH f.category as category, f.status as status, f.description as desc,
             f.completed_at as completed_at
        ORDER BY completed_at DESC
        RETURN category, status, desc, completed_at
        '''
        results = db_helper.run_query(cypher, {"project_path": project_dir})

        if not results:
            return None

        # Count by category and status
        planning_done = sum(1 for r in results if r.get("category") == "planning" and r.get("status") == "complete")
        planning_active = sum(1 for r in results if r.get("category") == "planning" and r.get("status") != "complete")
        meta_done = sum(1 for r in results if r.get("category") == "meta" and r.get("status") == "complete")
        meta_active = sum(1 for r in results if r.get("category") == "meta" and r.get("status") != "complete")

        total = len(results)
        if total == 0:
            return None

        # Get recent completed titles (last 3)
        recent = [r for r in results if r.get("status") == "complete"][:3]

        # Build low-context summary
        lines = ["## Planning & Meta Context"]
        lines.append(f"**Planning:** {planning_done} completed, {planning_active} active")
        lines.append(f"**Meta:** {meta_done} completed, {meta_active} active")

        if recent:
            lines.append("")
            lines.append("**Recent:**")
            for r in recent:
                desc = r.get("desc", "")[:50]
                cat = r.get("category", "")[:4]
                lines.append(f"- [{cat}] {desc}")

        lines.append("")
        lines.append("*Use `ijoka insight list` for detailed context or create new planning features as needed.*")

        return "\n".join(lines)

    except Exception:
        return None


def output_response(context: str, status_summary: str = None) -> None:
    """Output JSON response with context and optional terminal notification."""
    # Print status summary to stderr (visible in terminal)
    if status_summary:
        import sys
        print(f"\n📊 {status_summary}\n💡 Say 'hi' or 'status' to get a full update from Claude\n", file=sys.stderr)

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

    # Resolve project path using git-aware resolution
    # In Ijoka, PROJECT = GIT REPOSITORY - all subdirectories belong to the same project
    project_dir = resolve_project_path(
        cwd=hook_input.get("cwd"),
        env_var=os.environ.get("CLAUDE_PROJECT_DIR")
    )

    # Run quick diagnostics
    diagnostic_warnings = run_quick_diagnostics(project_dir)

    # Record session start in database
    db_helper.start_session(session_id, "claude-code", project_dir)

    # Capture the HEAD commit hash and set it on the session
    head_commit = get_head_commit(project_dir)
    if head_commit:
        db_helper.update_session_start_commit(session_id, head_commit)

    # Link this session to its predecessor if one exists
    link_to_previous_session(session_id, project_dir)

    # Record session start event (use session_id + event_type as unique ID for deduplication)
    db_helper.insert_event(
        event_type="SessionStart",
        source_agent="claude-code",
        session_id=session_id,
        project_dir=project_dir,
        payload={"action": "session_started", "diagnostics": diagnostic_warnings},
        event_id=f"{session_id}-SessionStart"
    )

    # Get features from graph database (single source of truth)
    features = db_helper.get_features(project_dir)

    if not features:
        output_response("No features found in graph database. Use `ijoka feature create` CLI command or import from ijoka-implementation-plan.yaml.")
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

        # Build rich context with previous session, step progress, and commits
        context_parts = []

        # CLI/API enforcement FIRST - Claude must see this before anything else
        context_parts.append(CLI_API_ENFORCEMENT)

        # Add previous session summary if available (what was done)
        prev_session = get_previous_session_summary(session_id, project_dir)
        has_history = prev_session is not None

        # Add step progress for active feature
        step_progress = get_step_progress(active_feature["id"])

        # Add recent commits for active feature
        recent_commits = get_recent_feature_commits(active_feature["id"])

        # Build the context
        context_parts.append(f"""## Session Continuity

**IMPORTANT:** At the start of this session, you MUST greet the user and provide a brief status update. Include:
1. What was accomplished in the previous session (if any)
2. Current feature and progress
3. What remains to be done
4. Ask the user what they would like to work on next

Do this BEFORE the user asks their first question.""")

        if prev_session:
            context_parts.append(prev_session)

        context_parts.append(f"""## Current Feature

**Working On:** {active_feature['description']}

**Overall Progress:** {completed}/{total} features complete ({percentage}%)""")

        if step_progress:
            context_parts.append(step_progress)

        if recent_commits:
            context_parts.append(recent_commits)

        # Get remaining features for "what's next" context
        remaining = [f for f in features if not f.get("passes") and f.get("id") != active_feature.get("id")]
        if remaining:
            next_features = remaining[:3]
            next_list = "\n".join([f"- {f['description'][:60]}" for f in next_features])
            context_parts.append(f"""## What's Next

After completing the current feature, these are queued:
{next_list}""")

        # Add planning/meta context summary (low-context awareness)
        planning_context = get_planning_context_summary(project_dir)
        if planning_context:
            context_parts.append(planning_context)

        # Add diagnostics if present
        if diagnostic_section:
            context_parts.append(diagnostic_section)

        # CLI/API enforcement already added FIRST (see above)

        context = "\n\n---\n\n".join(context_parts)

        # Build terminal status summary
        step_info = ""
        if step_progress:
            steps = db_helper.get_steps(active_feature["id"])
            if steps:
                done = sum(1 for s in steps if s.get("status") == "completed")
                step_info = f" | Steps: {done}/{len(steps)}"

        status_summary = f"Feature: {active_feature['description'][:50]} | Progress: {completed}/{total} ({percentage}%){step_info}"
        output_response(context, status_summary)
    else:
        # No active feature - show summary and ask user what to work on
        pending_features = [f for f in features if not f.get("passes")]

        # Format pending features
        feature_lines = []
        for i, f in enumerate(pending_features[:8]):
            priority = f.get("priority", 0)
            desc = f.get("description", "")[:55]
            feature_lines.append(f"{i+1}. {desc}")

        feature_summary = "\n".join(feature_lines) if feature_lines else "No pending features"

        # Add previous session summary if available
        prev_session = get_previous_session_summary(session_id, project_dir)
        prev_section = f"\n\n---\n\n{prev_session}" if prev_session else ""

        # CLI/API enforcement FIRST - Claude must see this before anything else
        context = f"""{CLI_API_ENFORCEMENT}

---

## Session Continuity

**IMPORTANT:** At the start of this session, you MUST greet the user and provide a brief status update. Include:
1. What was accomplished in the previous session (if any)
2. Overall project progress
3. Available features to work on
4. Ask the user what they would like to work on next

Do this BEFORE the user asks their first question.{prev_section}

---

## Project Status

**Progress:** {completed}/{total} features complete ({percentage}%)

**Pending Features:**
{feature_summary}

---

## How It Works

When you start working, the system will:
- Auto-match your work to an existing feature
- Auto-create a new feature if no match found
- Auto-complete features when criteria are met
"""
        # Add planning/meta context summary (low-context awareness)
        planning_context = get_planning_context_summary(project_dir)
        if planning_context:
            context += f"\n\n---\n\n{planning_context}"

        # Add diagnostics if present
        if diagnostic_section:
            context += diagnostic_section

        pending_count = len(pending_features)
        status_summary = f"No active feature | Progress: {completed}/{total} ({percentage}%) | {pending_count} pending"
        output_response(context, status_summary)


if __name__ == "__main__":
    main()
