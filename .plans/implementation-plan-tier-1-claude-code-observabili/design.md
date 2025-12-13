Excellent research results. Let me synthesize the findings and create the implementation plan.

---

## Research Synthesis

### Best Approach
**Hybrid: Plan-Aware Monitoring + Behavioral Drift Detection**

The industry is converging on OpenTelemetry-style semantic observability combined with plan-aware tracking. For Ijoka, this means:
- Track agent plans (via TodoWrite capture)
- Link tool calls to plan steps
- Detect drift when actions don't align with active step
- Surface feedback via existing hook `additionalContext`

### Critical Finding: Features ARE Plans
The codebase research revealed that **Features already serve as plans** with a `steps[]` array. TodoWrite is intentionally filtered out as a "meta-tool." This means:

| Spec Concept | Existing Implementation |
|--------------|------------------------|
| Plan | Feature (with steps[]) |
| Step | Feature.steps[i] (string array - flat) |
| ToolCall | Event (linked to Feature) |

**Gap:** Steps are flat strings, not trackable nodes. We need to upgrade steps from strings to proper nodes with status tracking.

### Patterns to Reuse
- `Event -[:LINKED_TO]-> Feature` relationship
- `work_count` increment pattern
- `additionalContext` hook response for feedback
- Deduplication via `event_id`/`tool_use_id`

### Schema Additions Needed
```
(:Step {id, description, status, order})
(:Plan)-[:HAS_STEP]->(:Step)
(:Event)-[:PART_OF_STEP]->(:Step)
```

### Signal Definitions (from spec in user message)

**Stuckness:**
- No FileChange or successful ToolCall for 3-5 min
- No step completion
- Repeated tool calls with similar args

**Drift:**
- ToolCalls/FileChanges unrelated to active Step
- Plan not updated while behavior shifts
- Sudden change in edited files

**Quality Gate:**
- Tests fail repeatedly
- Step changed many times

---

# Implementation Plan: Tier 1 Claude Code Observability

**Type:** Plan
**Status:** Ready
**Created:** 20251211-143000

---

## Overview

Implement semantic observability for Claude Code by capturing agent plans, linking tool calls to plan steps, detecting drift and stuckness, and surfacing real-time feedback. This transforms Ijoka from an activity logger into an agent observability platform.

---

## Plan Structure

```yaml
metadata:
  name: "Tier 1 Claude Code Observability"
  created: "20251211-143000"
  status: "ready"

overview: |
  Upgrade Ijoka's Claude Code integration from activity logging to semantic 
  observability. Capture plans via TodoWrite, track step progression, detect 
  drift/stuckness, and inject feedback via hooks.

research:
  approach: "Plan-aware monitoring with behavioral drift detection"
  libraries:
    - name: "neo4j (existing)"
      reason: "Already using Memgraph with Neo4j driver"
  patterns:
    - file: "packages/claude-plugin/hooks/scripts/track-event.py:302-469"
      description: "PostToolUse handler pattern with feature linking"
    - file: "packages/claude-plugin/hooks/scripts/graph_db_helper.py:549-623"
      description: "Event insertion with deduplication"
    - file: "packages/mcp-server/src/tools/handlers.ts:56-67"
      description: "MCP activity recording pattern"
  specifications:
    - requirement: "Stuckness: No progress for 3-5 min + repeated patterns"
      status: "must_follow"
    - requirement: "Drift: Actions unrelated to active step"
      status: "must_follow"
    - requirement: "Feedback via additionalContext in hook response"
      status: "must_follow"
  dependencies:
    existing:
      - "neo4j>=5.0 (Python)"
      - "Memgraph (Docker)"
    new: []

features:
  - "plan-capture"
  - "step-tracking"
  - "drift-detection"
  - "stuckness-detection"
  - "feedback-injection"

tasks:
  - id: "task-0"
    name: "Graph Schema Migration - Add Step Nodes"
    file: "tasks/task-0.md"
    priority: "blocker"
    dependencies: []

  - id: "task-1"
    name: "TodoWrite Hook - Capture Plans as Steps"
    file: "tasks/task-1.md"
    priority: "blocker"
    dependencies: ["task-0"]

  - id: "task-2"
    name: "Step↔Event Linking in PostToolUse"
    file: "tasks/task-2.md"
    priority: "high"
    dependencies: ["task-0", "task-1"]

  - id: "task-3"
    name: "Drift Detection Algorithm"
    file: "tasks/task-3.md"
    priority: "high"
    dependencies: ["task-2"]

  - id: "task-4"
    name: "Stuckness Detection Algorithm"
    file: "tasks/task-4.md"
    priority: "high"
    dependencies: ["task-2"]

  - id: "task-5"
    name: "Feedback Injection via additionalContext"
    file: "tasks/task-5.md"
    priority: "high"
    dependencies: ["task-3", "task-4"]

  - id: "task-6"
    name: "MCP Tools for Plan Management"
    file: "tasks/task-6.md"
    priority: "medium"
    dependencies: ["task-0", "task-1"]

shared_resources:
  files:
    - path: "packages/claude-plugin/hooks/scripts/graph_db_helper.py"
      reason: "Multiple tasks add functions"
      mitigation: "Task 0 adds schema first, others add functions sequentially"
    - path: "packages/claude-plugin/hooks/scripts/track-event.py"
      reason: "Tasks 2-5 modify PostToolUse handler"
      mitigation: "Sequential execution with clear function boundaries"
    - path: "packages/claude-plugin/hooks/hooks.json"
      reason: "Task 1 adds TodoWrite matcher"
      mitigation: "Single task modifies"

  databases:
    - name: "Memgraph"
      concern: "Schema changes during development"
      mitigation: "Use MERGE for idempotent operations"

testing:
  unit:
    - "Test plan capture from TodoWrite payload"
    - "Test step linking logic"
    - "Test drift score calculation"
    - "Test stuckness detection conditions"
  integration:
    - "End-to-end: TodoWrite → Plan → Step → Event → Feedback"
    - "Verify feedback appears in Claude responses"
  isolation:
    - "Each task tests independently"
    - "Mock Memgraph for unit tests"

success_criteria:
  - "TodoWrite captured as Plan with Step nodes"
  - "Tool calls linked to active Step"
  - "Drift detected when actions diverge from plan"
  - "Stuckness detected after 3-5 min no progress"
  - "Feedback injected via additionalContext"
  - "All existing functionality preserved"

notes: |
  Key insight: Features already serve as the "Plan" concept. We're adding
  Step nodes to make the steps[] array trackable with status and temporal data.
  
  TodoWrite is currently filtered out as a meta-tool. We'll capture it 
  specifically to extract the agent's plan structure.
  
  Drift detection uses semantic similarity between step description and 
  tool call context (file paths, tool type, etc).

changelog:
  - timestamp: "20251211-143000"
    event: "Plan created from research synthesis"
```

---

## Task Details

### Task 0: Graph Schema Migration - Add Step Nodes

```yaml
---
id: task-0
priority: blocker
status: pending
dependencies: []
labels:
  - parallel-execution
  - schema-change
  - priority-blocker
---
```

## 🎯 Objective

Add Step node type to the graph schema, enabling trackable plan steps with status, order, and temporal data. This replaces the flat `Feature.steps[]` string array with proper graph nodes.

## 🛠️ Implementation Approach

Extend `graph_db_helper.py` with Step node operations. Use MERGE for idempotent schema creation.

**Pattern to follow:**
- **File:** `graph_db_helper.py:367-418` - `create_feature()` pattern
- **Description:** Node creation with project linking

## 📁 Files to Touch

**Modify:**
- `packages/claude-plugin/hooks/scripts/graph_db_helper.py`
- `packages/mcp-server/src/db.ts`

## 🧪 Tests Required

**Unit:**
- [ ] Test Step node creation
- [ ] Test Step status transitions
- [ ] Test Step↔Feature relationship

## ✅ Acceptance Criteria

- [ ] Step node type exists with: id, description, status, order, expected_tools[], created_at, started_at, completed_at
- [ ] Relationship: `(:Step)-[:BELONGS_TO]->(:Feature)`
- [ ] Functions: `create_step()`, `get_steps()`, `update_step_status()`, `get_active_step()`
- [ ] Indexes on Step.feature_id for query performance

## 📝 Notes

Schema addition (Cypher):
```cypher
// Step node
CREATE (s:Step {
  id: $id,
  feature_id: $featureId,
  description: $description,
  status: 'pending',  // pending | in_progress | completed | skipped
  order: $order,
  expected_tools: $expectedTools,  // ['Edit', 'Write', 'Bash']
  created_at: datetime(),
  started_at: null,
  completed_at: null
})-[:BELONGS_TO]->(f:Feature {id: $featureId})
```

---

### Task 1: TodoWrite Hook - Capture Plans as Steps

```yaml
---
id: task-1
priority: blocker
status: pending
dependencies:
  - task-0
labels:
  - parallel-execution
  - hook-development
  - priority-blocker
---
```

## 🎯 Objective

Create a PostToolUse hook that captures TodoWrite calls and converts the todo list into Step nodes linked to the active Feature.

## 🛠️ Implementation Approach

Add TodoWrite-specific handler in `track-event.py`. When TodoWrite is detected:
1. Extract todos from `tool_input.todos`
2. Get or create Steps for each todo
3. Update step statuses based on todo statuses
4. Link to active Feature

**Pattern to follow:**
- **File:** `track-event.py:302-469` - `handle_post_tool_use()` pattern
- **Description:** Tool-specific payload extraction and graph storage

## 📁 Files to Touch

**Modify:**
- `packages/claude-plugin/hooks/scripts/track-event.py`
- `packages/claude-plugin/hooks/hooks.json` (if matcher needed)

**Create:**
- `packages/claude-plugin/hooks/scripts/capture-plan.py` (optional - could be inline)

## 🧪 Tests Required

**Unit:**
- [ ] Test todo extraction from payload
- [ ] Test Step creation from todos
- [ ] Test status sync (pending/in_progress/completed)

**Integration:**
- [ ] End-to-end TodoWrite → Steps in graph

## ✅ Acceptance Criteria

- [ ] TodoWrite calls create/update Step nodes
- [ ] Todo status maps to Step status: pending→pending, in_progress→in_progress, completed→completed
- [ ] Steps linked to active Feature
- [ ] Plan evolution tracked (new todos = new steps, removed todos = steps marked skipped)
- [ ] Deduplication via todo content hash

## 📝 Notes

TodoWrite payload structure:
```python
{
  "tool_input": {
    "todos": [
      {"content": "Task 1", "status": "pending", "activeForm": "Working on task 1"},
      {"content": "Task 2", "status": "in_progress", "activeForm": "Working on task 2"}
    ]
  }
}
```

Map to Steps:
```python
def handle_todowrite(hook_input, feature_id):
    todos = hook_input.get("tool_input", {}).get("todos", [])
    for i, todo in enumerate(todos):
        create_or_update_step(
            feature_id=feature_id,
            description=todo["content"],
            status=todo["status"],
            order=i
        )
```

---

### Task 2: Step↔Event Linking in PostToolUse

```yaml
---
id: task-2
priority: high
status: pending
dependencies:
  - task-0
  - task-1
labels:
  - parallel-execution
  - core-feature
  - priority-high
---
```

## 🎯 Objective

Link each tool call (Event) to the active Step, enabling plan-aware activity tracking. This is the foundation for drift detection.

## 🛠️ Implementation Approach

Modify `handle_post_tool_use()` to:
1. Get active Feature
2. Get active Step (status=in_progress) for that Feature
3. Create `(:Event)-[:PART_OF_STEP]->(:Step)` relationship
4. Auto-advance Step status when step work appears complete

**Pattern to follow:**
- **File:** `track-event.py:415-419` - Feature linking pattern
- **Description:** Add step_id to event insertion

## 📁 Files to Touch

**Modify:**
- `packages/claude-plugin/hooks/scripts/track-event.py`
- `packages/claude-plugin/hooks/scripts/graph_db_helper.py`

## 🧪 Tests Required

**Unit:**
- [ ] Test active step retrieval
- [ ] Test event-step linking
- [ ] Test step auto-advancement

## ✅ Acceptance Criteria

- [ ] Events have `step_id` when active step exists
- [ ] Relationship: `(:Event)-[:PART_OF_STEP]->(:Step)`
- [ ] Active step determined by: Feature's first in_progress step (by order)
- [ ] If no in_progress step, use first pending step

## 📝 Notes

```python
def get_active_step(feature_id: str) -> Optional[dict]:
    """Get the currently active step for a feature."""
    results = run_query("""
        MATCH (s:Step)-[:BELONGS_TO]->(f:Feature {id: $featureId})
        WHERE s.status = 'in_progress'
        RETURN s
        ORDER BY s.order ASC
        LIMIT 1
    """, {"featureId": feature_id})
    
    if not results:
        # Fall back to first pending step
        results = run_query("""
            MATCH (s:Step)-[:BELONGS_TO]->(f:Feature {id: $featureId})
            WHERE s.status = 'pending'
            RETURN s
            ORDER BY s.order ASC
            LIMIT 1
        """, {"featureId": feature_id})
    
    return _node_to_dict(results[0], "s") if results else None
```

---

### Task 3: Drift Detection Algorithm

```yaml
---
id: task-3
priority: high
status: pending
dependencies:
  - task-2
labels:
  - parallel-execution
  - signal-processing
  - priority-high
---
```

## 🎯 Objective

Implement drift detection that identifies when agent actions diverge from the current plan step. Returns a drift score and warning message.

## 🛠️ Implementation Approach

Calculate drift score based on:
1. **Tool alignment:** Is the tool type expected for this step?
2. **File alignment:** Are touched files related to step description?
3. **Temporal alignment:** Has the step been active too long without progress?

**Pattern to follow:**
- **File:** `track-event.py:248-289` - `generate_workflow_nudges()` pattern
- **Description:** Analyze context and return nudge messages

## 📁 Files to Touch

**Modify:**
- `packages/claude-plugin/hooks/scripts/track-event.py`
- `packages/claude-plugin/hooks/scripts/graph_db_helper.py`

## 🧪 Tests Required

**Unit:**
- [ ] Test drift score calculation
- [ ] Test tool alignment check
- [ ] Test file alignment check
- [ ] Test threshold triggering

## ✅ Acceptance Criteria

- [ ] Drift score: 0.0 (aligned) to 1.0 (drifted)
- [ ] Threshold: 0.7 triggers warning
- [ ] Warning message includes: current step, detected drift reason
- [ ] No false positives for legitimate exploratory work

## 📝 Notes

Algorithm:
```python
def calculate_drift(step: dict, event: dict) -> tuple[float, str]:
    """Calculate drift score and reason."""
    score = 0.0
    reasons = []
    
    step_desc = step.get("description", "").lower()
    tool_name = event.get("tool_name", "")
    file_paths = event.get("payload", {}).get("filePaths", [])
    
    # 1. Tool alignment (0.3 weight)
    expected_tools = step.get("expected_tools", [])
    if expected_tools and tool_name not in expected_tools:
        score += 0.3
        reasons.append(f"Unexpected tool: {tool_name}")
    
    # 2. File alignment (0.4 weight)
    # Extract keywords from step description
    step_keywords = extract_keywords(step_desc)
    file_keywords = extract_keywords(" ".join(file_paths))
    overlap = len(step_keywords & file_keywords) / max(len(step_keywords), 1)
    if overlap < 0.2:
        score += 0.4
        reasons.append(f"Files unrelated to step")
    
    # 3. Recent pattern (0.3 weight)
    # Check if last 5 events are all unrelated
    recent_drift_count = get_recent_drift_count(step["id"])
    if recent_drift_count >= 3:
        score += 0.3
        reasons.append(f"Sustained drift ({recent_drift_count} events)")
    
    return min(score, 1.0), "; ".join(reasons) if reasons else "aligned"
```

---

### Task 4: Stuckness Detection Algorithm

```yaml
---
id: task-4
priority: high
status: pending
dependencies:
  - task-2
labels:
  - parallel-execution
  - signal-processing
  - priority-high
---
```

## 🎯 Objective

Implement stuckness detection that identifies when an agent is making no meaningful progress. Triggers a warning to prompt the agent to summarize and refocus.

## 🛠️ Implementation Approach

Detect stuckness based on (from spec):
1. No FileChange or successful ToolCall for 3-5 minutes
2. No step completion
3. Repeated tool calls with similar arguments

**Pattern to follow:**
- **File:** `graph_db_helper.py:794-835` - `get_work_since_last_commit()` pattern
- **Description:** Time-based activity queries

## 📁 Files to Touch

**Modify:**
- `packages/claude-plugin/hooks/scripts/track-event.py`
- `packages/claude-plugin/hooks/scripts/graph_db_helper.py`

## 🧪 Tests Required

**Unit:**
- [ ] Test time-since-progress calculation
- [ ] Test repeated pattern detection
- [ ] Test stuckness threshold

## ✅ Acceptance Criteria

- [ ] Stuckness detected after 3 min no meaningful change
- [ ] Repeated patterns: 3+ similar tool calls in sequence
- [ ] Warning message: "You may be stuck. Summarize what you're trying to do."
- [ ] Configurable thresholds via environment variables

## 📝 Notes

Algorithm:
```python
def detect_stuckness(session_id: str, feature_id: str) -> tuple[bool, str]:
    """Detect if agent is stuck."""
    
    # 1. Time since last meaningful progress
    last_progress = get_last_meaningful_event(session_id)
    if last_progress:
        minutes_since = (now() - last_progress["timestamp"]).total_seconds() / 60
        if minutes_since > 3:
            return True, f"No progress for {int(minutes_since)} minutes"
    
    # 2. Repeated similar tool calls
    recent_events = get_recent_events(session_id, limit=10)
    patterns = find_repeated_patterns(recent_events)
    if patterns and patterns["count"] >= 3:
        return True, f"Repeated pattern: {patterns['description']}"
    
    # 3. Step stuck (in_progress for too long)
    active_step = get_active_step(feature_id)
    if active_step and active_step.get("started_at"):
        step_duration = (now() - active_step["started_at"]).total_seconds() / 60
        events_on_step = count_events_for_step(active_step["id"])
        if step_duration > 10 and events_on_step < 3:
            return True, f"Step '{active_step['description'][:30]}' stalled"
    
    return False, ""

def get_last_meaningful_event(session_id: str) -> Optional[dict]:
    """Get last event that indicates real progress."""
    results = run_query("""
        MATCH (e:Event)-[:TRIGGERED_BY]->(s:Session {id: $sessionId})
        WHERE e.tool_name IN ['Edit', 'Write'] 
        AND e.success = true
        RETURN e
        ORDER BY e.timestamp DESC
        LIMIT 1
    """, {"sessionId": session_id})
    return _node_to_dict(results[0], "e") if results else None
```

---

### Task 5: Feedback Injection via additionalContext

```yaml
---
id: task-5
priority: high
status: pending
dependencies:
  - task-3
  - task-4
labels:
  - parallel-execution
  - feedback-loop
  - priority-high
---
```

## 🎯 Objective

Inject drift and stuckness warnings into the hook response's `additionalContext` field, making alerts visible to the agent in real-time.

## 🛠️ Implementation Approach

Modify `handle_post_tool_use()` to:
1. Run drift detection
2. Run stuckness detection
3. Combine warnings
4. Return via `additionalContext` (existing pattern)

**Pattern to follow:**
- **File:** `track-event.py:464-469` - Nudge generation and return
- **File:** `track-event.py:729-732` - Response construction

## 📁 Files to Touch

**Modify:**
- `packages/claude-plugin/hooks/scripts/track-event.py`

## 🧪 Tests Required

**Unit:**
- [ ] Test warning message formatting
- [ ] Test multiple warnings combined
- [ ] Test no warnings when aligned

**Integration:**
- [ ] Verify additionalContext appears in Claude response

## ✅ Acceptance Criteria

- [ ] Drift warning: "⚠️ Drift detected: {reason}. Current step: {step}"
- [ ] Stuckness warning: "⚠️ Stuck: {reason}. Summarize what you're trying to do."
- [ ] Warnings appear in hook response `additionalContext`
- [ ] Rate limiting: Don't spam same warning repeatedly (use nudge tracking)

## 📝 Notes

```python
def generate_observability_feedback(
    session_id: str,
    feature_id: str,
    step: dict,
    event: dict
) -> list[str]:
    """Generate observability warnings for the agent."""
    warnings = []
    
    # Drift detection
    drift_score, drift_reason = calculate_drift(step, event)
    if drift_score > 0.7:
        if not has_been_nudged(session_id, f"drift:{step['id']}"):
            warnings.append(
                f"⚠️ Drift: {drift_reason}. "
                f"Current step: '{step['description'][:50]}'"
            )
            record_nudge(session_id, f"drift:{step['id']}")
    
    # Stuckness detection
    is_stuck, stuck_reason = detect_stuckness(session_id, feature_id)
    if is_stuck:
        if not has_been_nudged(session_id, "stuckness"):
            warnings.append(
                f"⚠️ Stuck: {stuck_reason}. "
                "Summarize what you're trying to do and your next step."
            )
            record_nudge(session_id, "stuckness")
    
    return warnings
```

---

### Task 6: MCP Tools for Plan Management

```yaml
---
id: task-6
priority: medium
status: pending
dependencies:
  - task-0
  - task-1
labels:
  - parallel-execution
  - mcp-tools
  - priority-medium
---
```

## 🎯 Objective

Add MCP tools for explicit plan management, allowing agents to declare intent and check status. Useful for Tier 2 agents (no hooks) and explicit agent participation.

## 🛠️ Implementation Approach

Add new MCP tools to `packages/mcp-server/`:
- `ijoka_set_plan`: Declare steps for current feature
- `ijoka_checkpoint`: Report progress, get feedback
- `ijoka_get_plan`: Retrieve current plan status

**Pattern to follow:**
- **File:** `packages/mcp-server/src/tools/handlers.ts:119-159` - Tool handler pattern
- **File:** `packages/mcp-server/src/tools/definitions.ts` - Tool definition pattern

## 📁 Files to Touch

**Modify:**
- `packages/mcp-server/src/tools/definitions.ts`
- `packages/mcp-server/src/tools/handlers.ts`
- `packages/mcp-server/src/db.ts`

## 🧪 Tests Required

**Unit:**
- [ ] Test ijoka_set_plan creates steps
- [ ] Test ijoka_checkpoint returns feedback
- [ ] Test ijoka_get_plan returns current status

## ✅ Acceptance Criteria

- [ ] `ijoka_set_plan` creates Step nodes from provided steps array
- [ ] `ijoka_checkpoint` returns drift/stuckness warnings
- [ ] `ijoka_get_plan` returns feature + steps with status
- [ ] Tools documented in tool definitions

## 📝 Notes

Tool definitions:
```typescript
{
  name: "ijoka_set_plan",
  description: "Declare your implementation plan for the current feature",
  parameters: {
    steps: {
      type: "array",
      items: { type: "string" },
      description: "Ordered list of implementation steps"
    }
  }
}

{
  name: "ijoka_checkpoint", 
  description: "Report progress and get feedback on current work",
  parameters: {
    step_completed: {
      type: "string",
      description: "Description of step just completed (optional)"
    },
    current_activity: {
      type: "string", 
      description: "What you're currently working on"
    }
  },
  returns: {
    drift_warning: "string | null",
    stuck_warning: "string | null",
    suggestions: "string[]"
  }
}
```

---

## References

- [OpenTelemetry AI Agent Observability](https://opentelemetry.io/blog/2025/ai-agent-observability/)
- [Claude Code Hooks Reference](https://code.claude.com/docs/en/hooks)
- [Ijoka Spec Sheet](user message above)
- Existing codebase patterns in `track-event.py`, `graph_db_helper.py`

---

## Plan Summary

📋 **Plan created in extraction-optimized format!**

**Plan Summary:**
- 7 total tasks
- 2 can run in parallel after task-0 (task-3 & task-4)
- 4 have dependencies (sequential)
- Conflict risk: **Low** (clear file boundaries)

**Tasks by Priority:**
- **Blocker:** task-0 (Schema), task-1 (TodoWrite Hook)
- **High:** task-2 (Step Linking), task-3 (Drift), task-4 (Stuckness), task-5 (Feedback)
- **Medium:** task-6 (MCP Tools)

**Execution Order:**
```
task-0 (Schema)
    ↓
task-1 (TodoWrite) ──┬──→ task-6 (MCP Tools)
    ↓               │
task-2 (Linking)    │
    ↓               │
┌───┴───┐           │
task-3  task-4      │  ← Can run in parallel!
└───┬───┘           │
    ↓               │
task-5 (Feedback) ←─┘
```

**What Happens Next:**

Ready to execute? I can start implementing task-0 (Graph Schema Migration) immediately, or you can run `/ctx:execute` to extract this plan to modular files for parallel development.