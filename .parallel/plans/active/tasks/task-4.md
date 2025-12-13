---
id: task-4
priority: medium
status: pending
dependencies: [task-2, task-3]
labels: [hooks, session-start, context]
---

# Context: Rich SessionStart output

## Objective

Enhance session-start.py additionalContext to show previous session summary, step progress, and recent commits.

## Implementation Approach

**Libraries:** Existing graph_db_helper functions

## Files to Touch

- `packages/claude-plugin/hooks/scripts/session-start.py` (modify)

## Implementation Details

```python
def get_previous_session_summary(current_session_id: str, project_id: str) -> Optional[str]:
    """Get summary of what the previous session accomplished."""
    cypher = '''
    MATCH (current:Session {id: $current_id})-[:CONTINUED_FROM]->(prev:Session)
    OPTIONAL MATCH (prev)-[:WORKED_ON]->(f:Feature)
    OPTIONAL MATCH (prev)-[:MADE_COMMITS]->(c:Commit)
    RETURN prev.id, collect(DISTINCT f.description) as features, 
           collect(DISTINCT c.message) as commits
    '''
    # Format as markdown


def get_step_progress(feature_id: str) -> Optional[str]:
    """Get current plan step progress."""
    cypher = '''
    MATCH (f:Feature {id: $feature_id})-[:HAS_STEP]->(s:Step)
    RETURN s.description, s.status, s.step_order ORDER BY s.step_order
    '''
    # Format as markdown with checkboxes


def get_recent_feature_commits(feature_id: str) -> Optional[str]:
    """Get recent commits for the active feature."""
    # Use get_feature_commits from graph_db_helper
    # Format as markdown list
```

## Expected Output

```markdown
## Previous Session Summary
**Worked on:** Implement login feature
**Commits:** 2 commit(s)

---

## Plan Progress
**Progress:** 2/5 steps (40%)
✅ Create login form
⏳ Integrate with API

---

## Recent Commits
- `abc1234` feat: add login form
```

## Acceptance Criteria

- [ ] Previous session summary shows features and commits
- [ ] Step progress shows completed/total with icons
- [ ] Recent commits shows last 3 with short hash
- [ ] All sections handle missing data gracefully
