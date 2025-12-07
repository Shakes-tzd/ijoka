#!/bin/bash
# AgentKanban Session End Hook
# Notifies the sync server that the session has ended

set -e

# Read hook input from stdin
INPUT=$(cat)

# Extract session info
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty')

# Sync server URL
SYNC_SERVER="${AGENTKANBAN_SERVER:-http://127.0.0.1:4000}"

# Get project directory
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Notify sync server of session end (redirect all output to prevent JSON contamination)
curl -s -X POST "${SYNC_SERVER}/sessions/end" \
    -H "Content-Type: application/json" \
    -d "{
        \"sessionId\": \"${SESSION_ID}\",
        \"sourceAgent\": \"claude-code\",
        \"projectDir\": \"${PROJECT_DIR}\"
    }" --max-time 2 >/dev/null 2>&1 || true

# Output response with correct hookEventName field
echo '{"hookSpecificOutput": {"hookEventName": "SessionEnd"}}'
