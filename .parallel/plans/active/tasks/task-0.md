---
id: task-0
priority: high
status: pending
dependencies: []
labels:
  - parallel-execution
  - alignment-system
---

# Task 0: Feature-Level Alignment Calculator

## Objective

Add a `calculate_feature_alignment()` function that works WITHOUT Steps, using feature description keywords to score alignment. This provides drift detection even when `ijoka_set_plan` wasn't called.

## Implementation Approach

Create a new function in track-event.py that:
1. Extracts keywords from active feature's `description` field
2. Compares against current tool activity (file paths, commands, patterns)
3. Returns alignment score 0.0-1.0

**Algorithm:**
```python
def calculate_feature_alignment(feature: dict, tool_name: str, tool_input: dict) -> tuple[float, str]:
    """Feature-level alignment when no Steps exist."""
    if not feature or feature.get("is_session_work"):
        return 1.0, "no_feature"  # Can't drift without feature
    
    feature_keywords = extract_keywords(feature.get("description", ""))
    activity_keywords = extract_activity_keywords(tool_name, tool_input)
    
    if not feature_keywords:
        return 1.0, "no_keywords"
    
    overlap = len(feature_keywords & activity_keywords)
    total = len(feature_keywords)
    
    if overlap / total >= 0.3:
        return 1.0, "aligned"
    elif overlap / total >= 0.1:
        return 0.7, f"weak_alignment ({overlap}/{total})"
    else:
        return 0.4, f"low_alignment ({overlap}/{total})"
```

**Pattern to follow:**
- File: `track-event.py:162` - existing `calculate_drift()` signature
- Match the (score, reason) return pattern

## Files to Touch

**Modify:**
- `packages/claude-plugin/hooks/scripts/track-event.py`
  - Add `calculate_feature_alignment()` function after line 214
  - Add `extract_activity_keywords()` helper function

## Tests Required

**Unit:**
- [ ] Test with feature "User authentication" + file "src/auth/login.ts" → high alignment
- [ ] Test with feature "User authentication" + file "src/database/migrations.ts" → low alignment
- [ ] Test with empty feature description → return 1.0 (can't judge)

## Acceptance Criteria

- [ ] Function returns (score, reason) tuple
- [ ] Score range: 0.0-1.0
- [ ] Works without Step nodes
- [ ] Handles edge cases (empty description, no keywords)
- [ ] Integrates with existing calculate_drift() as fallback

## Notes

This is the fallback mechanism when Steps don't exist. The existing `calculate_drift()` should call this when `get_active_step()` returns None.

---

**Worktree:** `worktrees/task-0`
**Branch:** `feature/task-0`
