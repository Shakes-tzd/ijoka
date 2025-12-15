# /complete-feature

Mark the currently active feature as complete in the Ijoka graph database.

## Usage

```
/complete-feature [summary]
```

Optionally provide a summary of what was accomplished.

## Instructions

When this command is invoked:

1. **Get current status** - Run `ijoka status` to find the active feature

2. **If no active feature**:
   - Report: "No feature is currently active"
   - Suggest: "Use `/next-feature` to start working on something"

3. **Verify completion** - Before marking complete, check:
   - Has work been done? (check for recent events/commits)
   - Are there pending plan steps? Run `ijoka plan show`
   - If incomplete plan, warn: "Plan has uncompleted steps. Mark complete anyway?"

4. **Complete the feature**:
   ```bash
   ijoka feature complete --summary "summary text"
   ```

5. **Show completion summary**:
   ```
   ## Feature Completed

   **Feature:** [description]
   **Summary:** [what was done]

   ### Progress
   - Completed: X/Y features (Z%)
   - Next up: [next pending feature]

   ### Suggested Actions
   - Run `/next-feature` to continue
   - Run `/feature-status` to see all features
   ```

6. **Suggest git commit** if changes haven't been committed:
   - Check for uncommitted changes
   - Offer to create a commit

## Important Notes

- Only mark a feature complete if the work is actually done
- If verification steps exist, they should have been tested
- The completion event is recorded in the graph for analytics
- Summary is important for session continuity

## Example Flow

```
User: /complete-feature Implemented OAuth flow with Google and GitHub providers

Claude:
## Feature Completed

**Feature:** User authentication with OAuth
**Summary:** Implemented OAuth flow with Google and GitHub providers

### Progress
- Completed: 6/12 features (50%)
- Next up: [security] Input validation and sanitization

### Suggested Actions
- Run `/next-feature` to continue with input validation
- You have uncommitted changes. Create a commit?
```
