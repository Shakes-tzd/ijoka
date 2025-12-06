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
        
        # Get next incomplete feature
        local next_feature=$(jq -r '[.[] | select(.passes == false)][0].description // "None"' "$feature_file")
        
        # Output context for Claude
        cat << EOF
{
    "hookSpecificOutput": {
        "additionalContext": "## Project Status\n\n**Progress:** ${completed}/${total} features complete (${percentage}%)\n\n**Next Feature:** ${next_feature}\n\n**Remember:**\n1. Pick ONE feature from feature_list.json where passes: false\n2. Implement and test thoroughly\n3. Update ONLY passes: false → true when complete\n4. Do NOT remove or edit existing features"
    }
}
EOF
    else
        # No feature list - suggest creating one
        cat << EOF
{
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
