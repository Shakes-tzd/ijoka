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

# Load feature list if it exists
load_features() {
    local feature_file="${PROJECT_DIR}/feature_list.json"

    if [ -f "$feature_file" ]; then
        # Count features
        local total=$(jq 'length' "$feature_file")
        local completed=$(jq '[.[] | select(.passes == true)] | length' "$feature_file")
        local remaining=$((total - completed))
        local percentage=0

        if [ "$total" -gt 0 ]; then
            percentage=$((completed * 100 / total))
        fi

        # Check for active feature (inProgress: true)
        local active_feature=$(jq -r '[.[] | select(.inProgress == true)][0].description // empty' "$feature_file")

        # Get next incomplete feature
        local next_feature=$(jq -r '[.[] | select(.passes == false and .inProgress != true)][0].description // "None"' "$feature_file")

        # Build feature list summary (top 10 features for context)
        local feature_summary=$(jq -r 'to_entries | .[:10] | .[] | "[\(.key)] \(if .value.passes then "✅" else "⬜" end) \(.value.description | .[0:60])"' "$feature_file" 2>/dev/null | tr '\n' '\\n')

        if [ -n "$active_feature" ]; then
            # Active feature exists - show it prominently
            cat << EOF
{
    "event": "SessionStart",
    "hookSpecificOutput": {
        "additionalContext": "## Active Feature\\n\\n**Currently Working On:** ${active_feature}\\n\\n**Progress:** ${completed}/${total} features complete (${percentage}%)\\n\\n**Important:** All tool calls in this session will be linked to this feature in AgentKanban.\\n\\n**BEFORE doing different work:** If the user's request relates to a DIFFERENT feature, you MUST update \`inProgress\` to the correct feature first. Use \`/set-feature\` or manually update feature_list.json.\\n\\n**When Done:**\\n1. Set \`inProgress: false\` and \`passes: true\` for the completed feature\\n2. Pick the next feature or run /next-feature"
    }
}
EOF
        else
            # No active feature - show feature list and prompt to set one
            cat << EOF
{
    "event": "SessionStart",
    "hookSpecificOutput": {
        "additionalContext": "## No Active Feature - Action Required\\n\\n**Progress:** ${completed}/${total} features complete (${percentage}%)\\n\\n**Features:**\\n${feature_summary}\\n\\n**CRITICAL:** Before ANY work, identify which feature it relates to:\\n\\n1. **New feature work:** Run \`/next-feature\` or set \`inProgress: true\` on an incomplete feature\\n2. **Fix/enhance completed feature:** Either reopen it (set \`passes: false\`) or create a follow-up\\n3. **Unrelated work:** Create a new feature first\\n\\n**Commands:**\\n- \`/next-feature\` - Auto-select next incomplete feature\\n- \`/set-feature <name>\` - Activate specific feature (even completed ones)\\n- \`/add-feature\` - Create new feature\\n\\n**Why This Matters:** Tool calls are ONLY linked to features when one has \`inProgress: true\`. Match your work to the right feature!"
    }
}
EOF
        fi
    else
        # No feature list - suggest creating one
        cat << EOF
{
    "event": "SessionStart",
    "hookSpecificOutput": {
        "additionalContext": "No feature_list.json found in this project. Consider creating one with /init-project command for structured task management."
    }
}
EOF
    fi
}

# Run in background to not block session start
notify_server &

# Load features and output context
load_features
