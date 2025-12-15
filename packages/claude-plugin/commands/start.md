# /ijoka:start

Session start command - provides context continuity and asks what to work on.

## What This Command Does

Run this at the start of every session to:
1. See what was accomplished in previous sessions
2. View current feature and progress
3. See step plan progress (if any)
4. See recent commits
5. Get asked what you'd like to work on next

## Usage

```
/ijoka:start
```

Run this command at the beginning of each Claude Code session for continuity.

## Instructions for Claude

When the user runs `/ijoka:start`, you MUST:

---

### ⚠️ CRITICAL: API-First for Agents

**Interface Hierarchy:**
| Interface | Audience | When to Use |
|-----------|----------|-------------|
| **REST API** | AI Agents | Primary - `curl http://localhost:8000/...` |
| **CLI** | Humans | Interactive terminal - `ijoka status` |

---

### FIRST ACTION: Call the REST API

**BEFORE doing anything else** - before reading files, running queries, or exploring the codebase:

```bash
# Get status (primary)
curl -s http://localhost:8000/status

# Get plan if active feature
curl -s http://localhost:8000/plan
```

**DO NOT** query databases directly or run Python scripts - use the API.

---

### 1. Get Current Status
Call `GET http://localhost:8000/status` to get:
- Current project info
- Active feature (if any)
- Overall progress statistics

### 2. Get Plan Progress (if active feature)
Call `GET http://localhost:8000/plan` to see:
- Step completion status
- Current step being worked on

### 3. Present Status Update

Format your response as follows:

```markdown
## Session Status

**Project:** {project_name}
**Progress:** {completed}/{total} features ({percentage}%)

---

### Previous Session
{If there was a previous session, summarize what was done. If no previous session data, say "First session in this project" or "No previous session data available"}

---

### Current Feature
**Working On:** {feature description}
**Status:** {in_progress/pending/blocked}

#### Plan Progress
{Show step checklist with status icons:}
- [x] Completed step
- [ ] Pending step (mark current with arrow: -> [ ] Current step)

---

### Recent Commits
{List last 3 commits if any, or "No commits in current feature"}

---

### What's Next
After completing current feature, these are queued:
1. {next feature 1}
2. {next feature 2}
3. {next feature 3}

---

## What would you like to work on?

Options:
1. Continue with current feature: "{feature description}"
2. Start a different feature
3. Review/update the plan
4. Something else
```

### 4. Wait for User Direction
After presenting the status, wait for the user to indicate what they want to do. Do NOT start working on anything until they respond.

## Example Interaction

**User:** `/ijoka:start`

**Claude:**
```
## Session Status

**Project:** ijoka
**Progress:** 5/21 features (24%)

---

### Previous Session
Completed implementation of git commit capture in PostToolUse hook. Made 2 commits:
- `abc1234` feat: add git commit detection
- `def5678` fix: handle edge cases in commit parsing

---

### Current Feature
**Working On:** Phase 2: Implement MCP tool definitions for 3-tier tool system
**Status:** in_progress

#### Plan Progress
- [x] Define ijoka_status tool (Tier 1)
- [x] Define lifecycle tools (Tier 2)
- -> [ ] Define insight tools (Tier 3)
- [ ] Export toolDefinitions array

---

### Recent Commits
- `abc1234` feat: add git commit detection
- `def5678` fix: handle edge cases

---

### What's Next
After completing current feature:
1. Phase 3: Implement handler functions
2. Add session ancestry tracking
3. Rich SessionStart context

---

## What would you like to work on?

Options:
1. Continue with current feature: "Phase 2: Implement MCP tool definitions"
2. Start a different feature
3. Review/update the plan
4. Something else
```

**User:** 1

**Claude:** *Continues working on the current feature...*
