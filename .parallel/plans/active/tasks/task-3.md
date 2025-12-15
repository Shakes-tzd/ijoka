---
id: task-3
priority: medium
status: pending
dependencies:
  - task-2
labels:
  - sequential
  - alignment-system
---

# Task 3: Session Work Accumulator Alert

## Objective

Alert when too many events accumulate in Session Work without being attributed to a real feature. This catches drift at the session level.

## Implementation Approach

1. **Add counter function to graph_db_helper.py:**
```python
def get_session_work_event_count(project_path: str, session_id: str) -> int:
    """Count events in Session Work for current session."""
    results = run_query("""
        MATCH (e:Event)-[:LINKED_TO]->(f:Feature)
        WHERE f.is_session_work = true
        AND e.session_id = $sessionId
        RETURN count(e) as count
    """, {"sessionId": session_id})
    return results[0].get("count", 0) if results else 0
```

2. **Add nudge in generate_workflow_nudges():**
```python
# Session Work accumulator alert
session_work_count = db_helper.get_session_work_event_count(project_path, session_id)
if session_work_count > 20:
    if not db_helper.has_been_nudged(session_id, "session_work_accumulator"):
        nudges.append(
            f"Note: {session_work_count} events in this session aren't linked to a feature. "
            "Consider using ijoka_discover_feature to create a feature for this work."
        )
        db_helper.record_nudge(session_id, "session_work_accumulator")
```

**Pattern to follow:**
- File: `track-event.py:428` - commit reminder nudge pattern
- Same structure, different trigger condition

## Files to Touch

**Modify:**
- `packages/claude-plugin/hooks/scripts/graph_db_helper.py`
  - Add `get_session_work_event_count()` function
- `packages/claude-plugin/hooks/scripts/track-event.py`
  - Add Session Work alert to `generate_workflow_nudges()`

## Tests Required

**Unit:**
- [ ] Test count function returns correct value
- [ ] Test threshold (>20 triggers, <=20 doesn't)

**Integration:**
- [ ] Work without declaring feature → alert after 20+ events
- [ ] Alert only shown once per session

## Acceptance Criteria

- [ ] Alert triggers when Session Work > 20 events
- [ ] Alert suggests ijoka_discover_feature
- [ ] Alert not repeated in same session
- [ ] Count query is efficient (<10ms)

## Notes

This catches the pattern we observed: 759 events in Session Work. The alert prompts Claude to properly attribute work.

---

**Worktree:** `worktrees/task-3`
**Branch:** `feature/task-3`
