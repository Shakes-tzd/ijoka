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

# Notify sync server of session end
curl -s -X POST "${SYNC_SERVER}/sessions/end" \
    -H "Content-Type: application/json" \
    -d "{
        \"sessionId\": \"${SESSION_ID}\"
    }" --max-time 2 2>/dev/null || true

# Output response with event field
echo '{"event": "SessionEnd", "continue": true}'
