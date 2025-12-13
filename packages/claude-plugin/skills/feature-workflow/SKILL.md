# Feature Workflow Skill

This skill provides guidance for working with Ijoka's graph-based feature management system following Anthropic's long-running agent pattern.

## When This Skill Activates

Activate this skill when:
- User asks about project tasks or features
- User wants to track progress on a project
- Starting a new coding session in a project
- User needs help with feature management workflow

## The Pattern

Ijoka uses **Memgraph** (graph database) as the single source of truth for features, sessions, and activity. This solves the core challenge of long-running agents: maintaining context across multiple sessions.

**Interface:** Use the `ijoka` CLI or REST API (port 8000) for all operations. MCP is deprecated.

### Data Architecture

```
┌──────────────────┐
│    MEMGRAPH      │ ◄── SOURCE OF TRUTH
│   (Graph DB)     │     bolt://localhost:7687
│                  │
│  • Projects      │
│  • Features      │
│  • Sessions      │
│  • Events        │
│  • Steps (plans) │
└──────────────────┘
```

### Feature Structure (in Graph)

```
(Feature)
  - id: UUID
  - description: "Human-readable description"
  - category: functional|ui|security|etc
  - status: pending|in_progress|complete|blocked
  - priority: integer (higher = more urgent)
  - steps: ["Step 1", "Step 2"]
  - work_count: number of linked events
```

### Categories

- **functional** - Core functionality
- **ui** - User interface components
- **security** - Security features
- **performance** - Performance optimizations
- **documentation** - Documentation tasks
- **testing** - Test coverage
- **infrastructure** - DevOps/infrastructure
- **refactoring** - Code improvements
- **planning** - Research, design, discovery work
- **meta** - Tooling, observability, workflow improvements

## CRITICAL: Activity Tracking

**All tool calls are automatically linked to the active feature (status: in_progress) in Ijoka.**

This means:
- If no feature is active, activities go to "Session Work" pseudo-feature
- If the wrong feature is active, activities are misattributed
- You MUST ensure the correct feature is active before doing any work

## Workflow

### At Session Start

1. Run `/ijoka:start` or `ijoka status`
2. Check overall progress (X/Y complete)
3. Identify the active feature (status: in_progress)
4. Review the plan if one exists (`ijoka plan show`)

### BEFORE Any Work (CRITICAL)

Before implementing anything, you MUST:

1. **Analyze the user's request** - What are they asking for?
2. **Check features via `ijoka status`** - Does this relate to an existing feature?
3. **Match to a feature** - Find the most relevant feature by:
   - Keywords in descriptions
   - Category match
   - Related functionality
4. **Handle completed features** - If work relates to a completed feature:
   - **Option A**: Reopen it (`ijoka feature start <ID>`)
   - **Option B**: Create a follow-up feature (`ijoka feature create`)
5. **Set the active feature** - Run `ijoka feature start <ID>` on the correct feature

### Working on Completed Features

If a user asks to fix/enhance something related to a completed feature:

```
User: "Fix the login form validation"

Claude:
1. Runs `ijoka status`... "User authentication" is marked complete
2. This relates to that feature
3. Ask user:
   "This relates to 'User authentication' which is complete.
   Should I:
   A) Reopen it for this fix
   B) Create a new bug-fix feature"
4. Run `ijoka feature start <ID>` accordingly
5. Proceed with the fix (now properly tracked)
```

### During Session

1. Ensure correct feature has status: in_progress
2. Optionally set a plan with `ijoka plan set`
3. Implement the feature thoroughly
4. Use `ijoka checkpoint` to report progress
5. Test using the verification steps
6. When complete:
   - Run `ijoka feature complete`
7. Commit the code changes

### Critical Rules

> "It is unacceptable to remove or edit tests because this could lead to missing or buggy functionality."

1. **ALWAYS set a feature active** before doing work
2. **Match work to features** - Do not assume the active feature is correct
3. **Reopen or create follow-ups** for work on completed features
4. **Work on ONE feature** at a time
5. **Complete fully** before marking as done
6. **Leave code in working state** at session end
7. **Commit frequently** - Use `ijoka checkpoint` to track progress

## CLI Commands (REQUIRED Interface)

**CRITICAL: ALWAYS use `ijoka` CLI commands for ALL Ijoka operations.**

Never bypass the CLI by:
- Calling Python scripts directly (e.g., `uv run graph_db_helper.py`)
- Running database queries directly
- Using internal APIs

The CLI provides validation, audit trails, and a consistent interface.

| Command | Purpose |
|---------|---------|
| `ijoka status` | Get project status, active features, progress |
| `ijoka feature list` | List all features with status |
| `ijoka feature start [ID]` | Start working on a feature |
| `ijoka feature complete` | Mark feature as complete |
| `ijoka feature block --reason` | Report a blocker |
| `ijoka feature create` | Create a new feature |
| `ijoka plan set` | Declare implementation steps |
| `ijoka plan show` | Get current plan status |
| `ijoka checkpoint` | Report progress, get feedback |
| `ijoka insight record` | Save a reusable learning |
| `ijoka insight list` | Retrieve relevant insights |
| `ijoka analytics digest` | Get daily insights digest |
| `ijoka analytics ask` | Natural language query |

Add `--json` to any command for JSON output (useful for parsing).

**REST API Alternative (http://localhost:8000):**
Start with `ijoka-server`, then use standard HTTP requests.

⚠️ **MCP Server is DEPRECATED** - Use CLI or REST API instead.

## Commands Available

- `/ijoka:start` - Session start with status and next actions
- `/init-project` - Initialize Ijoka for a new project
- `/feature-status` - Show progress and next tasks
- `/next-feature` - Start the next pending feature
- `/add-feature` - Create a new feature
- `/complete-feature` - Mark current feature complete
- `/set-feature` - Switch to a specific feature
- `/migrate` - Import from legacy feature_list.json

## Example Session Flow

```
Session Start:
→ Run /ijoka:start or `ijoka status`
→ "Progress: 5/12 features complete (42%)"
→ "Active: [security] Input validation"
→ "Plan: 2/4 steps complete"

Working:
→ Claude continues with "Input validation" feature
→ Runs `ijoka checkpoint` after each step
→ Tests validation thoroughly
→ Runs `ijoka feature complete`
→ Commits code

Session End:
→ Code is in working state
→ Progress: 6/12 (50%)
→ Next session can continue seamlessly
```

## Migration from feature_list.json

If you encounter a project with `feature_list.json`:
1. Run `/migrate` to import features to graph database
2. The file will be renamed to `feature_list.json.migrated`
3. All future work uses the graph database
