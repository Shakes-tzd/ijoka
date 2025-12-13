# Fix Bug Command

Report and fix a bug with proper attribution to the correct feature.

## Usage

```
/ijoka:fix-bug <description>
```

## What This Does

⚠️ **Note:** MCP server is deprecated. Use CLI commands when MCP tools are unavailable.

1. Gets current project context (`ijoka status` CLI OR `ijoka_status` MCP)
2. Identifies which feature the bug relates to:
   - If a feature is actively in progress and the bug is related to it, stay on that feature
   - If the bug is in a different feature, ask user to confirm switching
3. Records the bug fix attempt with proper event linking

## Instructions

When the user reports a bug with `/fix-bug`:

1. First, understand the bug by asking clarifying questions if needed:
   - What is the expected behavior?
   - What is the actual behavior?
   - How to reproduce?

2. Check current feature context (`ijoka status` CLI OR `ijoka_status` MCP):
   - If there's an active feature, determine if the bug relates to it
   - If not, search for the related feature

3. Before fixing:
   - Confirm the fix approach with the user
   - If switching features, use `ijoka feature start <ID>` CLI OR `ijoka_start_feature` MCP

4. After fixing:
   - Test the fix
   - If tests pass, consider completing the bug fix
   - Use `ijoka insight record` CLI OR `ijoka_record_insight` MCP to document the fix if it's a pattern others might encounter

## Example

User: `/fix-bug Button nesting causes hydration error`

You should:
1. Get current status
2. Identify this relates to UI/frontend work
3. Find the root cause (button inside button)
4. Fix with proper HTML structure
5. Verify the fix works
