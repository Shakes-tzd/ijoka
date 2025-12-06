# Feature Workflow Skill

This skill provides guidance for working with `feature_list.json` files following Anthropic's long-running agent pattern.

## When This Skill Activates

This skill should be used when:
- A `feature_list.json` file exists in the project
- User asks about project tasks or features
- User wants to track progress on a project
- Starting a new coding session in a project

## The Pattern

`feature_list.json` is a persistent task queue that survives across sessions. It solves the core challenge of long-running agents: maintaining context across multiple sessions.

### File Structure

```json
[
  {
    "category": "functional",
    "description": "Human-readable description of what the feature does",
    "steps": ["Step 1", "Step 2", "Step 3"],
    "passes": false
  }
]
```

### Fields

- **category**: Groups features (functional, ui, security, performance, documentation, testing, infrastructure, refactoring)
- **description**: What the feature does (human-readable)
- **steps**: How to verify it works (test script for agent)
- **passes**: `false` = not done, `true` = done

### Optional Fields

- **inProgress**: `true` if currently being worked on
- **agent**: Which agent is working on this feature

## Workflow

### At Session Start

1. Read `feature_list.json`
2. Check overall progress (X/Y complete)
3. Identify features where `passes: false`
4. Note any features with `inProgress: true`

### During Session

1. Pick ONE feature where `passes: false`
2. Set `inProgress: true` on that feature
3. Implement the feature thoroughly
4. Test using the verification steps
5. When complete:
   - Set `passes: true`
   - Set `inProgress: false`
6. Commit the code changes

### Critical Rules

> "It is unacceptable to remove or edit tests because this could lead to missing or buggy functionality."

1. **NEVER remove features** from the list
2. **NEVER edit feature descriptions** or steps
3. **ONLY modify** `passes` and `inProgress` fields
4. **Work on ONE feature** at a time
5. **Complete fully** before marking as done
6. **Leave code in working state** at session end

## Why JSON Not Markdown?

> "After experimentation, we landed on using JSON for this, as the model is less likely to inappropriately change or overwrite JSON files compared to Markdown files."

JSON feels like data. Markdown feels editable. Claude is more careful with structured data.

## Commands Available

- `/init-project` - Create feature_list.json
- `/feature-status` - Show progress and next tasks
- `/next-feature` - Start the next incomplete feature

## Integration with AgentKanban

When AgentKanban is running:
- Features sync to the desktop kanban board
- Progress updates trigger notifications
- Activity is logged to the timeline
- Multiple agents can be coordinated

## Example Session Flow

```
Session Start:
→ Hook loads feature_list.json
→ "Progress: 5/12 features complete (42%)"
→ "Next: [security] Input validation"

Working:
→ Claude picks up "Input validation" feature
→ Sets inProgress: true
→ Implements validation middleware
→ Tests against verification steps
→ Sets passes: true, inProgress: false
→ Commits code

Session End:
→ Code is in working state
→ Progress: 6/12 (50%)
→ Next session can continue seamlessly
```
