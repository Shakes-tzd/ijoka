#!/usr/bin/env bash
set -euo pipefail

PLAN_FILE=".parallel/plans/active/plan.yaml"
if [ ! -f "$PLAN_FILE" ]; then
  echo "Error: plan.yaml not found at $PLAN_FILE"
  exit 1
fi

# Extract task IDs using grep
TASK_IDS=$(grep "  - id:" "$PLAN_FILE" | sed 's/.*id: *"\([^"]*\)".*/\1/')

echo "Creating worktrees for $(echo "$TASK_IDS" | wc -l | tr -d ' ') tasks..."

echo "$TASK_IDS" | while read task_id; do
  [ -z "$task_id" ] && continue
  branch="feature/$task_id"
  worktree="worktrees/$task_id"

  if [ -d "$worktree" ]; then
    echo "⚠️  Worktree exists: $task_id"
  elif git show-ref --verify --quiet refs/heads/$branch 2>/dev/null; then
    git worktree add "$worktree" "$branch" 2>/dev/null && echo "✅ Created: $task_id (existing branch)"
  else
    git worktree add "$worktree" -b "$branch" 2>/dev/null && echo "✅ Created: $task_id (new branch)"
  fi
done

echo ""
echo "✅ Setup complete! Active worktrees:"
git worktree list | grep -E "worktrees/|phoenix" || true
