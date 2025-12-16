# /ijoka:start

Session start command - provides context continuity and asks what to work on.

## What This Command Does

Run this at the start of every session to:
1. See project status and WIP
2. View current feature(s) and progress
3. See step plan progress (if any)
4. See recent commits
5. Get asked what you'd like to work on next

## Usage

```
/ijoka:start
```

## Instructions for Claude

When the user runs `/ijoka:start`, follow the **Ijoka Development Process**.

See the `ijoka-development-process` skill for complete workflow documentation.
See `IJOKA_POLICY.md` in the plugin for full policy details.

---

### FIRST ACTION: Call the REST API

**BEFORE doing anything else:**

```bash
# Get status (primary)
curl -s http://localhost:8000/status

# Get plan if active feature
curl -s http://localhost:8000/plan

# Get recent commits
git log --oneline -5
```

---

### Present Status Update

Format your response as follows:

```markdown
## Session Status

**Project:** {project_name}
**Progress:** {completed}/{total} features ({percentage}%)
**Active Features (WIP):** {count of in_progress features}

---

### Previous Session
{Summarize what was done, or "First session"}

---

### Current Feature(s)
**Working On:** {feature description(s)}
**Status:** in_progress

#### Plan Progress
- [x] Completed step
- [ ] Pending step

---

### Recent Commits
{List last 3-5 commits}

---

### What's Next
After completing current feature(s):
1. {next feature}
2. {next feature}

---

## What would you like to work on?

Options:
1. Continue with current feature
2. Start a different feature
3. Review/update the plan
4. Create new work item (/add-feature, /bug, /spike)
5. Something else
```

### Wait for User Direction

After presenting the status, wait for the user to indicate what they want to do.

---

## Key Reminders

1. **Parallel development OK** - Up to 3 features can be in progress (WIP limit)
2. **Use Ijoka for tasks** - `/plan` command, NOT internal TodoWrite
3. **Finish over start** - Complete existing work before starting new
4. **All activity tracked** - Hooks attribute work to features automatically
