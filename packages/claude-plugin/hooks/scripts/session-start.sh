#!/bin/bash
# AgentKanban Session Start Hook
# Loads feature_list.json context and notifies the sync server

set -e

# Read hook input from stdin
INPUT=$(cat)

# Extract session info
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Sync server URL (AgentKanban desktop app)
SYNC_SERVER="${AGENTKANBAN_SERVER:-http://127.0.0.1:4000}"

# Notify sync server of session start
notify_server() {
    curl -s -X POST "${SYNC_SERVER}/sessions/start" \
        -H "Content-Type: application/json" \
        -d "{
            \"sessionId\": \"${SESSION_ID}\",
            \"sourceAgent\": \"claude-code\",
            \"projectDir\": \"${PROJECT_DIR}\"
        }" --max-time 2 2>/dev/null || true
}

# Output JSON response using jq for proper escaping
output_response() {
    local context="$1"
    jq -c -n --arg ctx "$context" '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
}

# Load feature list if it exists
load_features() {
    local feature_file="${PROJECT_DIR}/feature_list.json"

    if [ -f "$feature_file" ]; then
        # Count features
        local total=$(jq 'length' "$feature_file")
        local completed=$(jq '[.[] | select(.passes == true)] | length' "$feature_file")
        local percentage=0

        if [ "$total" -gt 0 ]; then
            percentage=$((completed * 100 / total))
        fi

        # Check for active feature (inProgress: true)
        local active_feature=$(jq -r '[.[] | select(.inProgress == true)][0].description // empty' "$feature_file")

        # Get next incomplete feature
        local next_feature=$(jq -r '[.[] | select(.passes == false and .inProgress != true)][0].description // "None"' "$feature_file")

        if [ -n "$active_feature" ]; then
            # Active feature exists - show it prominently
            local context="## Active Feature

**Currently Working On:** ${active_feature}

**Progress:** ${completed}/${total} features complete (${percentage}%)

**Important:** All tool calls in this session will be linked to this feature in AgentKanban.

**BEFORE doing different work:** If the user's request relates to a DIFFERENT feature, you MUST update \`inProgress\` to the correct feature first. Use \`/set-feature\` or manually update feature_list.json.

**When Done:**
1. Set \`inProgress: false\` and \`passes: true\` for the completed feature
2. Pick the next feature or run /next-feature"
            output_response "$context"
        else
            # No active feature - show feature list and prompt to set one
            local feature_summary=$(jq -r 'to_entries | .[:10] | .[] | "[\(.key)] \(if .value.passes then "✅" else "⬜" end) \(.value.description | .[0:60])"' "$feature_file" 2>/dev/null | head -10)

            local context="## No Active Feature - Action Required

**Progress:** ${completed}/${total} features complete (${percentage}%)

**Features:**
${feature_summary}

**CRITICAL:** Before ANY work, identify which feature it relates to:

1. **New feature work:** Run \`/next-feature\` or set \`inProgress: true\` on an incomplete feature
2. **Fix/enhance completed feature:** Either reopen it (set \`passes: false\`) or create a follow-up
3. **Unrelated work:** Create a new feature first

**Commands:**
- \`/next-feature\` - Auto-select next incomplete feature
- \`/set-feature <name>\` - Activate specific feature (even completed ones)
- \`/add-feature\` - Create new feature

**Why This Matters:** Tool calls are ONLY linked to features when one has \`inProgress: true\`. Match your work to the right feature!"
            output_response "$context"
        fi
    else
        # No feature list - suggest creating one
        output_response "No feature_list.json found in this project. Consider creating one with /init-project command for structured task management."
    fi
}

# Run in background to not block session start
# Redirect all output to /dev/null to prevent contaminating JSON stdout
notify_server >/dev/null 2>&1 &

# Load features and output context
load_features
