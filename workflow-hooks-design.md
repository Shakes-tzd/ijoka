# Workflow Hooks Design: Nudging Good Practices

## Philosophy

Hooks should **guide, not dictate**. They provide:
1. **Situational awareness** - What's the current state?
2. **Gentle reminders** - What should happen next?
3. **Guardrails** - Prevent common mistakes

The goal is to offload workflow management from the user while keeping Claude's decision-making agency.

---

## Current Hook Points

| Hook | Trigger | Current Use | Opportunity |
|------|---------|-------------|-------------|
| `SessionStart` | Session begins | Show active feature | Add workflow context |
| `PostToolUse` | After any tool | Track events | Detect patterns, nudge commits |
| `UserPromptSubmit` | User sends message | Feature classification | Detect intent, suggest workflow |
| `Stop` | Session ends | Record end | Summarize work, remind commits |
| `PreToolUse` | Before tool runs | Validation | Guard against drift |

---

## Proposed Workflow Nudges

### 1. Commit Frequency Reminder (PostToolUse)

**Problem**: Work piles up without commits, risking lost progress.

**Detection**:
```python
# In track-event.py PostToolUse handler
def check_commit_reminder(project_dir: str, session_id: str) -> str | None:
    """Check if a commit reminder is needed."""

    # Get recent work tools (Edit, Write) since last commit
    results = db_helper.run_query("""
        MATCH (e:Event)-[:TRIGGERED_BY]->(s:Session {id: $sessionId})
        WHERE e.tool_name IN ['Edit', 'Write']
        AND e.timestamp > COALESCE(
            (SELECT MAX(e2.timestamp) FROM Event e2
             WHERE e2.tool_name = 'Bash' AND e2.payload CONTAINS 'git commit'),
            datetime('1970-01-01')
        )
        RETURN count(e) as work_count
    """, {"sessionId": session_id})

    work_count = results[0]['work_count'] if results else 0

    # Nudge after 5+ file changes without commit
    if work_count >= 5:
        return f"You've made {work_count} file changes since last commit. Consider committing your progress."

    return None
```

**Output**: Add to hook response as `additionalContext`:
```
💡 You've made 7 file changes since last commit. Consider committing your progress.
```

### 2. Feature Drift Detection (PostToolUse)

**Problem**: Work drifts away from the active feature.

**Detection**:
```python
def detect_feature_drift(tool_name: str, tool_input: dict, active_feature: dict) -> str | None:
    """Detect if work is drifting from the active feature."""

    # Skip for meta tools
    if tool_name.startswith("mcp__ijoka"):
        return None

    # Get file paths from tool
    file_paths = extract_file_paths(tool_input)
    if not file_paths:
        return None

    # Check if files match feature's expected areas
    feature_keywords = extract_keywords(active_feature['description'])
    file_keywords = extract_keywords_from_paths(file_paths)

    overlap = len(feature_keywords & file_keywords)
    if overlap == 0 and len(file_keywords) > 0:
        return f"Working on files unrelated to active feature '{active_feature['description'][:40]}...'. Consider switching features or staying focused."

    return None
```

### 3. Feature Completion Prompt (PostToolUse)

**Problem**: Features sit in "in_progress" forever.

**Detection**:
```python
def check_feature_completion(active_feature: dict, tool_name: str, tool_result: dict) -> str | None:
    """Suggest completing feature after successful test/build."""

    if tool_name != "Bash":
        return None

    # Check if this looks like a successful test/build
    cmd = tool_result.get("command", "").lower()
    output = tool_result.get("output", "").lower()

    is_test_command = any(x in cmd for x in ["test", "pytest", "jest", "vitest"])
    is_build_command = any(x in cmd for x in ["build", "compile", "cargo build"])
    looks_successful = "passed" in output or "success" in output or tool_result.get("exit_code") == 0

    if (is_test_command or is_build_command) and looks_successful:
        return f"Tests/build passed! If feature '{active_feature['description'][:30]}...' is complete, use `ijoka_complete_feature`."

    return None
```

### 4. Session End Summary (Stop hook)

**Problem**: Sessions end without summary or commit.

**Output**:
```python
def generate_session_summary(session_id: str, project_dir: str) -> str:
    """Generate end-of-session summary with actionable items."""

    # Get session stats
    stats = get_session_stats(session_id)

    summary = f"""
## Session Summary

**Work Done:**
- {stats['edit_count']} files edited
- {stats['feature_progress']} features touched
- {stats['event_count']} total tool calls

**Uncommitted Changes:** {stats['uncommitted_count']} files
"""

    if stats['uncommitted_count'] > 0:
        summary += "\n⚠️ **Action Needed**: You have uncommitted changes. Consider committing before ending."

    if stats['feature_in_progress']:
        summary += f"\n📌 **Active Feature**: {stats['feature_in_progress']} (still in progress)"

    return summary
```

### 5. New Feature Guidance (on feature start)

**Problem**: Features get started without clear scope.

**Trigger**: When `ijoka_start_feature` is called

**Output** (injected into next response):
```
## Starting Feature: {description}

**Verification Steps:**
{steps}

**Workflow Reminder:**
1. Make incremental changes
2. Commit after each logical unit
3. Run tests before completing
4. Call `ijoka_complete_feature` when done
```

---

## Implementation Plan

### Phase 1: Commit Reminders
- Add `work_since_commit` counter to session state
- Reset on git commit detection
- Nudge after 5+ changes

### Phase 2: Feature Lifecycle
- Track feature start/complete timing
- Detect stale features (in_progress > 1 hour with no activity)
- Prompt for completion after test pass

### Phase 3: Session Bookends
- Enhanced session start with workflow checklist
- Session end summary with action items

### Phase 4: Drift Detection
- Keyword extraction from features and file paths
- Gentle warning when work diverges
- Option to switch features or acknowledge tangent

---

## Hook Response Structure

```python
class HookResponse:
    # Standard fields
    hookEventName: str
    additionalContext: str  # Markdown injected into conversation

    # New workflow fields
    nudges: list[str]  # Gentle reminders (shown as tips)
    warnings: list[str]  # More urgent (shown prominently)
    suggestions: list[str]  # Actionable items

    # Workflow state
    workflowState: dict  # For UI display
        # uncommitted_changes: int
        # feature_time_elapsed: str
        # session_duration: str
```

---

## Key Principles

1. **Non-blocking**: Nudges are informational, not gates
2. **Contextual**: Only show relevant reminders
3. **Actionable**: Include the command/action to take
4. **Respectful**: Don't nag - once per trigger type per session
5. **Configurable**: Users can disable specific nudges

---

## Questions to Resolve

1. **Persistence**: How do we track "already nudged about X" across tool calls?
   - Option A: Session state in graph
   - Option B: In-memory in hook process (resets each call)
   - Option C: File-based flag in project

2. **Frequency**: How often to nudge?
   - Commit reminder: Every 5 file changes
   - Feature completion: Once per test pass
   - Drift warning: Once per unrelated file cluster

3. **Override**: Can user say "stop reminding me about commits"?
   - Per-session flag
   - Per-project config
   - Global user preference
