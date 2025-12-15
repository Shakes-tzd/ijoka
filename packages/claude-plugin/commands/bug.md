# /bug

Report a bug discovered during work.

## Usage

```
/bug <description>
```

## What This Does

Creates a new bug work item linked to the currently active feature as its parent.
Bugs are categorized as "functional" by default with priority 70 (high).

## Behavior

1. Get active feature via `curl -s http://localhost:8000/features/active`
2. Create bug: `ijoka feature create functional "<description>" --type bug --priority 70`
3. If an active feature exists, link it as parent: `curl -X POST http://localhost:8000/features/{bug_id}/link/{active_feature_id}`
4. Output: Bug ID and link to parent

## Instructions

Run these commands to create a bug:

```bash
# 1. Get current active feature
ACTIVE=$(curl -s http://localhost:8000/features/active | jq -r '.features[0].id // empty')

# 2. Create the bug
BUG_RESPONSE=$(ijoka feature create functional "$ARGUMENTS" --type bug --priority 70 --json)
BUG_ID=$(echo "$BUG_RESPONSE" | jq -r '.feature.id')

# 3. Link to active feature if exists
if [ -n "$ACTIVE" ]; then
  curl -s -X POST "http://localhost:8000/features/$BUG_ID/link/$ACTIVE"
  echo "Bug $BUG_ID created and linked to feature $ACTIVE"
else
  echo "Bug $BUG_ID created (no active feature to link)"
fi
```

## Example

```
/bug TypeError in authentication flow when token expires
```

Creates a bug with description "TypeError in authentication flow when token expires"
linked as a child of the current active feature.

## When to Use

- When you encounter an error during development
- When you discover broken functionality
- When tests fail due to a bug (not a missing implementation)
- To track issues found during code review
