# /ijoka:end

Session end command - ensures proper handoff for the next session.

## What This Command Does

Run this at the end of every session to:
1. Summarize what was accomplished
2. Record any blockers or pending work
3. Capture handoff notes for the next session
4. Ensure code is in a good state (committed or documented)
5. Update feature status if needed

## Usage

```
/ijoka:end
```

Run this command before ending your Claude Code session.

## Instructions for Claude

When the user runs `/ijoka:end`, you MUST follow this process:

### 1. Gather Session Information

**Check git status:**
```bash
git status --short
git log --oneline -5
git diff --stat HEAD 2>/dev/null | tail -5
```

**Get current feature status:**
Run `ijoka status` to get:
- Active feature info
- Session event count
- Plan progress (if any)

### 2. Summarize Accomplishments

Review the session and identify:
- Features completed or progressed
- Files modified
- Commits made
- Tests run/fixed
- Bugs encountered and resolved

### 3. Identify Pending Work

Check for:
- Uncommitted changes (git status)
- Incomplete todos
- Known issues or blockers
- Next steps that weren't started

### 4. Present Handoff Summary

Format your response as follows:

```markdown
## Session End Summary

**Session Duration:** {approximate based on activity}
**Feature:** {active feature description}

---

### Accomplishments

{Bullet list of what was done:}
- Implemented X functionality
- Fixed Y bug
- Added Z test coverage
- Refactored W component

### Commits Made

{List commits from this session:}
- `abc1234` feat: description
- `def5678` fix: description

### Code State

{One of:}
- All changes committed - code is in a clean state
- **Uncommitted changes:** {count} files modified - consider committing before ending
- **Work in progress:** {description of incomplete work}

### Pending/Next Steps

{What the next session should focus on:}
1. {Next step 1}
2. {Next step 2}
3. {Next step 3}

### Blockers (if any)

{Any issues blocking progress:}
- {Blocker description and potential solutions}

---

## Handoff Notes

{Key context the next session needs to know:}
- {Important decision made and why}
- {Gotcha or caveat discovered}
- {Relevant file locations}

---

## Recommended Actions Before Closing

{Based on state, recommend:}
- [ ] Commit uncommitted changes
- [ ] Push to remote
- [ ] Update feature status (complete/blocked)
- [ ] Record insight for future reference
```

### 5. Offer Actions

After presenting the summary, offer these options:

```markdown
## Before you go, would you like to:

1. **Commit changes** - I'll help create a commit with a good message
2. **Mark feature complete** - If the feature is done
3. **Mark feature blocked** - If there's a blocker
4. **Record an insight** - Capture something learned for future reference
5. **Just end** - Everything is in order

Which would you like to do? (or just close the session)
```

### 6. Execute Requested Actions

If the user chooses an action:

**Option 1 (Commit):**
- Run `git status` and `git diff`
- Generate appropriate commit message
- Stage and commit changes
- Offer to push

**Option 2 (Complete):**
- Run `ijoka feature complete`
- Confirm completion

**Option 3 (Blocked):**
- Ask for blocker description
- Run `ijoka feature block --reason "..."`

**Option 4 (Insight):**
- Ask what they learned
- Run `ijoka insight record`
- Categorize appropriately (pattern, gotcha, decision, etc.)

**Option 5 (Just end):**
- Confirm session is ending
- Wish them well

## Example Interaction

**User:** `/ijoka:end`

**Claude:**
```
## Session End Summary

**Session Duration:** ~45 minutes
**Feature:** Implement drift detection alignment system

---

### Accomplishments

- Designed 4-task alignment system architecture
- Implemented parallel execution using git worktrees
- Created calculate_feature_alignment() for step-less drift detection
- Added Session Work accumulator alert (>20 events)
- Wired drift warnings to additionalContext
- Added comprehensive logging to TodoWrite pipeline
- Fixed integration - alignment fallback now active

### Commits Made

- `0e1042b` fix: integrate calculate_feature_alignment as fallback
- `2d60b38` Merge branch 'feature/task-3'
- `39f6c63` Merge branch 'feature/task-2'
- `e61d013` Merge branch 'feature/task-1'
- `30ed712` Merge branch 'feature/task-0'

### Code State

All changes committed - code is in a clean state

### Pending/Next Steps

1. Test drift detection in real usage
2. Tune thresholds (currently 0.7 for warnings, 20 for Session Work)
3. Add feature-level alignment to drift warning message generation

### Blockers

None - implementation complete

---

## Handoff Notes

- Drift detection works at TWO levels now:
  - Step-level (precise) when ijoka_set_plan was used
  - Feature-level (keyword) as fallback when no Steps
- The 0.7 threshold may need tuning based on real usage
- Debug logging added to TodoWrite pipeline - can be reduced later

---

## Recommended Actions Before Closing

- [x] All changes committed
- [ ] Push to remote (optional)
- [ ] Consider marking feature complete

---

## Before you go, would you like to:

1. **Push changes** - Push to origin/phoenix-liveview-migration
2. **Mark feature complete** - Drift detection is working
3. **Record an insight** - Capture learnings about drift detection
4. **Just end** - Everything is in order
```

**User:** 1

**Claude:** *Pushes changes and confirms*

## Important Notes

- Always check for uncommitted changes before ending
- Encourage proper handoff documentation
- The next session can use `/ijoka:start` to pick up where this left off
- Insights recorded here will appear in future session context
