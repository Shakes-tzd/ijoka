<thinking>
Excellent! All 5 research agents have completed. Let me synthesize the findings and create the modular YAML plan.

Key findings from research:
1. **Drift detection code already exists** in track-event.py (lines 162-214) - calculate_drift() function
2. **TodoWrite handling exists** - handle_todowrite() and sync_steps_from_todos() already implemented
3. **The issue is NOT missing code** - it's that the existing code isn't being triggered properly
4. **driftScore IS being calculated** but not stored on Event nodes (only in payload)
5. **Nudge system exists** - has_been_nudged/record_nudge pattern ready to use

The real problem identified:
- Steps are rarely created because ijoka_set_plan isn't called
- TodoWrite sync exists but may not be creating Steps properly
- Drift warnings aren't being surfaced via additionalContext

So the tasks should focus on:
1. **Fix TodoWrite → Steps sync** - Ensure it actually creates Steps
2. **Add Feature-Level Alignment** - Work without Steps as fallback
3. **Wire up drift warnings** - Connect existing calculate_drift to additionalContext
4. **Add Session Work accumulator** - Alert when too many events go there

Let me create the modular plan now.
</thinking>

## Research Synthesis

### Key Finding: Infrastructure Exists But Isn't Wired Up

| Component | Status | Location |
|-----------|--------|----------|
| `calculate_drift()` | ✅ Exists | track-event.py:162-214 |
| `handle_todowrite()` | ✅ Exists | track-event.py:460-510 |
| `sync_steps_from_todos()` | ✅ Exists | graph_db_helper.py:869-900 |
| `generate_drift_warning()` | ✅ Exists | track-event.py:217-224 |
| Nudge tracking | ✅ Exists | graph_db_helper.py:1353-1377 |
| **Drift → additionalContext** | ❌ Not wired | Need to connect |
| **Feature-level alignment** | ❌ Missing | Need to add fallback |
| **Session Work alerts** | ❌ Missing | Need to implement |

### Architectural Decision

**The problem isn't missing code—it's missing wiring and fallbacks.**

1. TodoWrite → Steps sync exists but Steps aren't being queried for drift
2. Drift is calculated but warnings aren't surfaced via additionalContext
3. No fallback when Steps don't exist (feature-level alignment)

---

# Implementation Plan: Alignment System

**Type:** Plan
**Status:** Ready
**Created:** 20251213-143000

---

## Overview

Wire up existing drift detection infrastructure, add feature-level alignment as fallback when Steps don't exist, and surface warnings via additionalContext. Estimated ~1 session of work since most code already exists.

---

## Plan Structure

```yaml
metadata:
  name: "Alignment System"
  created: "20251213-143000"
  status: "ready"

overview: |
  Wire up existing drift detection code, add feature-level alignment fallback,
  and surface warnings via additionalContext. Most infrastructure exists - 
  this plan connects the pieces and adds missing fallbacks.

research:
  approach: "Hybrid Plan-Observation with keyword alignment (no embeddings)"
  libraries:
    - name: "None needed"
      reason: "All dependencies already in place"
  patterns:
    - file: "packages/claude-plugin/hooks/scripts/track-event.py:162"
      description: "Existing calculate_drift() function"
    - file: "packages/claude-plugin/hooks/scripts/track-event.py:460"
      description: "Existing handle_todowrite() function"
    - file: "packages/claude-plugin/hooks/scripts/graph_db_helper.py:1353"
      description: "Nudge tracking pattern (has_been_nudged/record_nudge)"
  specifications:
    - requirement: "Drift score 0.0-1.0 (1.0 = aligned)"
      status: "must_follow"
    - requirement: "Warning threshold >= 0.7 drift"
      status: "must_follow"
    - requirement: "No embeddings or external services"
      status: "must_follow"
  dependencies:
    existing:
      - "neo4j (Memgraph driver)"
      - "re (regex for keyword extraction)"
    new: []

features:
  - "feature-level-alignment"
  - "todowrite-step-verification"
  - "drift-warning-injection"
  - "session-work-accumulator"

tasks:
  - id: "task-0"
    name: "Feature-Level Alignment Calculator"
    file: "tasks/task-0.md"
    priority: "high"
    dependencies: []

  - id: "task-1"
    name: "Verify TodoWrite → Steps Sync"
    file: "tasks/task-1.md"
    priority: "high"
    dependencies: []

  - id: "task-2"
    name: "Wire Drift Warnings to additionalContext"
    file: "tasks/task-2.md"
    priority: "blocker"
    dependencies: []

  - id: "task-3"
    name: "Session Work Accumulator Alert"
    file: "tasks/task-3.md"
    priority: "medium"
    dependencies: ["task-2"]

shared_resources:
  files:
    - path: "packages/claude-plugin/hooks/scripts/track-event.py"
      reason: "Tasks 0, 1, 2, 3 all modify this file"
      mitigation: "Sequential execution for tasks touching same functions"
    - path: "packages/claude-plugin/hooks/scripts/graph_db_helper.py"
      reason: "Tasks 0, 3 add new functions"
      mitigation: "Add functions at end of file, no conflicts"

testing:
  unit:
    - "Test calculate_feature_alignment() with various feature descriptions"
    - "Test Session Work event counting"
  integration:
    - "Verify drift warnings appear in Claude responses"
    - "Verify TodoWrite creates Steps"
  isolation:
    - "Each task can be tested independently"

success_criteria:
  - "Drift score recorded on >80% of events"
  - "Warnings surface when drift >= 0.7"
  - "Session Work alert when > 20 events unattributed"
  - "No regression in existing hook performance (<50ms added)"

notes: |
  Most code already exists! This plan focuses on:
  1. Wiring existing pieces together
  2. Adding feature-level fallback for when Steps don't exist
  3. Surfacing warnings that are currently calculated but hidden

changelog:
  - timestamp: "20251213-143000"
    event: "Plan created from ctx:architect design"
```

---

## Task Details

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

## 🎯 Objective

Add a `calculate_feature_alignment()` function that works WITHOUT Steps, using feature description keywords to score alignment. This provides drift detection even when `ijoka_set_plan` wasn't called.

## 🛠️ Implementation Approach

Create a new function that:
1. Extracts keywords from active feature's `description` field
2. Compares against current tool activity (file paths, commands, patterns)
3. Returns alignment score 0.0-1.0

**Algorithm:**
```python
def calculate_feature_alignment(feature: dict, tool_name: str, tool_input: dict) -> tuple[float, str]:
    """Feature-level alignment when no Steps exist."""
    if not feature:
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
- **File:** `track-event.py:162` - existing `calculate_drift()` signature
- **Description:** Match the (score, reason) return pattern

## 📁 Files to Touch

**Modify:**
- `packages/claude-plugin/hooks/scripts/track-event.py`
  - Add `calculate_feature_alignment()` function after line 214
  - Add `extract_activity_keywords()` helper

## 🧪 Tests Required

**Unit:**
- [ ] Test with feature "User authentication" + file "src/auth/login.ts" → high alignment
- [ ] Test with feature "User authentication" + file "src/database/migrations.ts" → low alignment
- [ ] Test with empty feature description → return 1.0 (can't judge)

## ✅ Acceptance Criteria

- [ ] Function returns (score, reason) tuple
- [ ] Score range: 0.0-1.0
- [ ] Works without Step nodes
- [ ] Handles edge cases (empty description, no keywords)

## 📝 Notes

This is the fallback mechanism when Steps don't exist. The existing `calculate_drift()` should call this when `get_active_step()` returns None.

---

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

## 🎯 Objective

Verify that `handle_todowrite()` actually creates Step nodes, and fix any issues preventing Steps from being created.

## 🛠️ Implementation Approach

1. **Trace the flow:**
   - `handle_todowrite()` (track-event.py:460) calls `sync_steps_from_todos()`
   - `sync_steps_from_todos()` (graph_db_helper.py:869) should create Steps

2. **Add logging/verification:**
   - Add debug output to confirm Steps are created
   - Query database after TodoWrite to verify

3. **Fix issues:**
   - Check if feature_id is being passed correctly
   - Verify Cypher queries are executing

**Pattern to follow:**
- **File:** `graph_db_helper.py:869` - existing sync function
- **Description:** Add verification and fix any bugs

## 📁 Files to Touch

**Modify:**
- `packages/claude-plugin/hooks/scripts/track-event.py`
  - Add verification after sync_steps_from_todos() call
- `packages/claude-plugin/hooks/scripts/graph_db_helper.py`
  - Debug/fix sync_steps_from_todos() if needed

## 🧪 Tests Required

**Integration:**
- [ ] Call TodoWrite with 3 todos → verify 3 Steps created in Memgraph
- [ ] Update todo status → verify Step status updates
- [ ] Remove todo → verify Step marked as skipped

## ✅ Acceptance Criteria

- [ ] TodoWrite calls create Step nodes
- [ ] Steps linked to active Feature via :BELONGS_TO
- [ ] Step status syncs with todo status
- [ ] No duplicate Steps on repeated TodoWrite

## 📝 Notes

Research showed TodoWrite handling exists but we found 0 driftScore recorded, suggesting Steps may not be created. This task verifies and fixes the pipeline.

---

---
id: task-2
priority: blocker
status: pending
dependencies: []
labels:
  - parallel-execution
  - alignment-system
  - critical-path
---

# Task 2: Wire Drift Warnings to additionalContext

## 🎯 Objective

Connect existing `calculate_drift()` and `generate_drift_warning()` to the additionalContext output so warnings actually appear in Claude's responses.

## 🛠️ Implementation Approach

1. **Locate the gap:**
   - Drift is calculated at line 707: `drift_score, drift_reason = calculate_drift(...)`
   - Warning text generated but never added to nudges

2. **Wire it up in `generate_workflow_nudges()`:**
```python
def generate_workflow_nudges(payload, session_id, feature, step):
    nudges = []
    
    # Existing nudges (commit reminder, etc.)
    ...
    
    # NEW: Drift warning
    drift_score = payload.get("driftScore", 0)
    if drift_score >= 0.7 and step:
        nudge_key = f"drift_warning_{step.get('id', 'unknown')}"
        if not db_helper.has_been_nudged(session_id, nudge_key):
            warning = generate_drift_warning(step, drift_score, payload.get("driftReason", ""))
            if warning:
                nudges.append(warning)
                db_helper.record_nudge(session_id, nudge_key)
    
    return nudges
```

3. **Ensure nudges reach additionalContext:**
   - Verify `hookSpecificOutput["additionalContext"]` is set

**Pattern to follow:**
- **File:** `track-event.py:406` - existing `generate_workflow_nudges()`
- **Description:** Add drift warning alongside commit reminder

## 📁 Files to Touch

**Modify:**
- `packages/claude-plugin/hooks/scripts/track-event.py`
  - Update `generate_workflow_nudges()` to include drift warnings
  - Pass drift data from payload to nudge generator

## 🧪 Tests Required

**Integration:**
- [ ] Trigger high drift (work on unrelated files) → warning appears
- [ ] Warning only shown once per step (nudge tracking)
- [ ] No warning when drift < 0.7

## ✅ Acceptance Criteria

- [ ] Drift warnings appear in additionalContext when score >= 0.7
- [ ] Warnings not repeated (per-step nudge tracking)
- [ ] Warning includes step description and drift reason
- [ ] No performance regression

## ⚠️ Potential Conflicts

**Files:**
- `track-event.py` - Other tasks also modify → Execute this first as blocker

## 📝 Notes

This is the critical missing piece. Drift is calculated but never surfaced. This task makes it visible.

---

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

## 🎯 Objective

Alert when too many events accumulate in Session Work without being attributed to a real feature. This catches drift at the session level.

## 🛠️ Implementation Approach

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
- **File:** `track-event.py:428` - commit reminder nudge pattern
- **Description:** Same structure, different trigger condition

## 📁 Files to Touch

**Modify:**
- `packages/claude-plugin/hooks/scripts/graph_db_helper.py`
  - Add `get_session_work_event_count()` function
- `packages/claude-plugin/hooks/scripts/track-event.py`
  - Add Session Work alert to `generate_workflow_nudges()`

## 🧪 Tests Required

**Unit:**
- [ ] Test count function returns correct value
- [ ] Test threshold (>20 triggers, <=20 doesn't)

**Integration:**
- [ ] Work without declaring feature → alert after 20+ events
- [ ] Alert only shown once per session

## ✅ Acceptance Criteria

- [ ] Alert triggers when Session Work > 20 events
- [ ] Alert suggests ijoka_discover_feature
- [ ] Alert not repeated in same session
- [ ] Count query is efficient (<10ms)

## 📝 Notes

This catches the pattern we observed: 759 events in Session Work. The alert prompts Claude to properly attribute work.

---

## References

- [Anthropic Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [OpenTelemetry AI Agent Observability](https://opentelemetry.io/blog/2025/ai-agent-observability/)
- Existing code: `packages/claude-plugin/hooks/scripts/track-event.py`
- Existing code: `packages/claude-plugin/hooks/scripts/graph_db_helper.py`

---

📋 **Plan created in extraction-optimized format!**

**Plan Summary:**
- 4 total tasks
- 3 can run in parallel (Tasks 0, 1, 2)
- 1 has dependencies (Task 3 needs Task 2)
- Conflict risk: **Low** (same file but different functions)

**Tasks by Priority:**
- **Blocker:** task-2 (Wire Drift Warnings)
- **High:** task-0, task-1
- **Medium:** task-3

**Key Insight:** Most code already exists! This plan wires existing pieces together.

**Next Steps:**
1. Review the plan above
2. Request changes if needed
3. Run `/ctx:execute` to extract and start parallel development

Ready to execute? Run `/ctx:execute` to extract and start implementation.