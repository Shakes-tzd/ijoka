# /set-feature

Explicitly set the active feature for activity tracking in the Ijoka graph database.

## When to Use

- When starting work that relates to a specific feature
- When the user's request relates to an existing feature (even if completed)
- When you need to reopen a completed feature for additional work
- When switching between features

## Usage

```
/set-feature <description or ID>
```

Examples:
- `/set-feature User authentication` - Match by description
- `/set-feature abc123` - Set by feature ID
- `/set-feature security:input` - Match security features containing "input"

## What This Command Does

1. Queries Memgraph for matching features via `ijoka_status`
2. Finds the best match based on input
3. If feature is complete, offers options:
   - A) Reopen it (set back to in_progress)
   - B) Create a follow-up feature
4. Calls `ijoka_start_feature` to activate the target feature
5. Confirms the switch

## Instructions for Claude

When the user runs this command or when you identify work relates to a specific feature:

1. **Get all features** - Call `ijoka_status`

2. **Match the input** (from $ARGUMENTS) to a feature by:
   - Exact ID match
   - Partial description match (fuzzy)
   - Category prefix (e.g., "security:0" = first security feature)

3. **If no match found**:
   - List similar features if any
   - Offer to create new feature with `/add-feature`

4. **If matching a completed feature**:
   ```
   This feature is marked complete:
   - "User authentication with OAuth"

   Options:
   A) Reopen for additional work (bug fix, enhancement)
   B) Create follow-up: "Fix/enhance: User authentication with OAuth"
   ```
   - Wait for user choice before proceeding

5. **Activate the feature** - Call `ijoka_start_feature` with the feature_id
   - This automatically deactivates any other active feature

6. **Confirm**: "Now tracking activity for: [feature description]"

## Smart Feature Detection

Before working on any task, Claude should proactively:

1. **Analyze the user's request** - What are they asking for?
2. **Check features via ijoka_status** - Does this relate to an existing feature?
3. **Match by keywords** - Look for overlapping terms in descriptions
4. **Consider completed features** - If the request relates to a "done" feature, use this command

## Example Flow

```
User: "Fix the bug in the login form"

Claude thinks:
- User is asking to fix something in login
- Check features... "User authentication" exists and is complete
- This work relates to that feature
- Should run /set-feature to track properly

Claude: "This relates to the 'User authentication' feature which is marked complete.
Should I:
A) Reopen it for this bug fix
B) Create a new 'Bug fix: Login form issue' feature"

User: "A"

Claude: [Calls ijoka_start_feature to reopen]
Claude: "Now tracking activity for: User authentication with OAuth"
[Proceeds to fix the bug, all tool calls are linked to this feature]
```

## Proactive Feature Management

Claude should proactively manage features by:

1. **At session start**: Check if there's an active feature
2. **Before any work**: Identify which feature the work relates to
3. **For new work**: Either find matching feature or create new one
4. **For fixes/enhancements**: Use /set-feature to properly attribute work

This ensures ALL activity is properly linked to features in Ijoka.
