---
id: task-1
priority: high
status: pending
dependencies: []
labels:
  - parallel-execution
  - alignment-system
---

# Task 1: Verify TodoWrite → Steps Sync

## Objective

Verify that `handle_todowrite()` actually creates Step nodes, and fix any issues preventing Steps from being created.

## Implementation Approach

1. **Trace the flow:**
   - `handle_todowrite()` (track-event.py:460) calls `sync_steps_from_todos()`
   - `sync_steps_from_todos()` (graph_db_helper.py:869) should create Steps

2. **Add logging/verification:**
   - Add debug output to confirm Steps are created
   - Query database after TodoWrite to verify

3. **Fix issues found:**
   - Check if feature_id is being passed correctly
   - Verify Cypher queries are executing
   - Ensure Steps are linked to Features with :BELONGS_TO

**Pattern to follow:**
- File: `graph_db_helper.py:869` - existing sync function
- Add verification and fix any bugs

## Files to Touch

**Modify:**
- `packages/claude-plugin/hooks/scripts/track-event.py`
  - Add verification after sync_steps_from_todos() call
  - Log step creation results
- `packages/claude-plugin/hooks/scripts/graph_db_helper.py`
  - Debug/fix sync_steps_from_todos() if needed
  - Ensure proper Step node creation

## Tests Required

**Integration:**
- [ ] Call TodoWrite with 3 todos → verify 3 Steps created in Memgraph
- [ ] Update todo status → verify Step status updates
- [ ] Remove todo → verify Step marked as skipped

## Acceptance Criteria

- [ ] TodoWrite calls create Step nodes in Memgraph
- [ ] Steps linked to active Feature via :BELONGS_TO
- [ ] Step status syncs with todo status
- [ ] No duplicate Steps on repeated TodoWrite
- [ ] Logging shows step creation for debugging

## Notes

Research showed TodoWrite handling exists but we found 0 driftScore recorded, suggesting Steps may not be created. This task verifies and fixes the pipeline.

---

**Worktree:** `worktrees/task-1`
**Branch:** `feature/task-1`
