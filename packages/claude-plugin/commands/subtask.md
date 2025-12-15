# /subtask

Break down the current feature into smaller tasks.

## Usage

```
/subtask <description>
```

## What This Does

Creates a new feature as a child of the currently active feature.
This is for decomposing large features into smaller, manageable pieces.

The subtask inherits the category from its parent but can be overridden.

## Behavior

1. Get active feature via `ijoka status`
2. If no active feature, show error
3. Create subtask: `ijoka feature create <parent_category> "<description>" --priority <parent_priority - 10>`
4. Link to active feature as parent
5. Output: Subtask ID, parent link, progress indicator

## Instructions

Run these commands to create a subtask:

```bash
# 1. Get current active feature (REQUIRED)
ACTIVE_RESPONSE=$(curl -s http://localhost:8000/features/active)
ACTIVE=$(echo "$ACTIVE_RESPONSE" | jq -r '.features[0].id // empty')
CATEGORY=$(echo "$ACTIVE_RESPONSE" | jq -r '.features[0].category // "functional"')
PRIORITY=$(echo "$ACTIVE_RESPONSE" | jq -r '.features[0].priority // 100')
PARENT_DESC=$(echo "$ACTIVE_RESPONSE" | jq -r '.features[0].description // "Unknown"' | head -c 50)

if [ -z "$ACTIVE" ]; then
  echo "Error: No active feature. Start a feature first with 'ijoka feature start <id>'"
  exit 1
fi

# 2. Create the subtask with lower priority
SUB_PRIORITY=$((PRIORITY - 10))
SUB_RESPONSE=$(ijoka feature create "$CATEGORY" "$ARGUMENTS" --priority "$SUB_PRIORITY" --json)
SUB_ID=$(echo "$SUB_RESPONSE" | jq -r '.feature.id')

# 3. Link to parent feature
curl -s -X POST "http://localhost:8000/features/$SUB_ID/link/$ACTIVE"

# 4. Get updated tree to show progress
TREE=$(curl -s "http://localhost:8000/features/$ACTIVE/tree")
CHILD_COUNT=$(echo "$TREE" | jq -r '.tree.child_count')

echo "Subtask $SUB_ID created under '$PARENT_DESC...'"
echo "Parent now has $CHILD_COUNT subtask(s)"
```

## Example

```
/subtask Add unit tests for authentication module
```

If working on "User Authentication System", this creates a subtask linked to it.

## When to Use

- When a feature is too large to complete in one session
- When you identify distinct phases of work
- When multiple components need separate tracking
- When you want granular progress visibility
- For task decomposition during planning

## Viewing Subtasks

See all subtasks for the current feature:

```bash
curl -s http://localhost:8000/features/{parent_id}/children | jq '.children[].description'
```
