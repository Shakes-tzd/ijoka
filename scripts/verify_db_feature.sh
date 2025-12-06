#!/bin/bash

DB_PATH="$HOME/Library/Application Support/com.agentkanban.app/agentkanban.db"
API_URL="http://127.0.0.1:4000"

echo "Teardown: Stopping any running instances"
# We can't easily kill the tauri app from here without knowing PID, assuming user has it running as per request

echo "Step 1: Checking DB existence"
if [ ! -f "$DB_PATH" ]; then
    echo "❌ Database file not found at $DB_PATH. Make sure the app is running."
    exit 1
fi
echo "✅ Database file exists."

echo "Step 2: Checking DB Schema"
TABLES=$(sqlite3 "$DB_PATH" ".tables")
REQUIRED_TABLES="events features sessions config"
for table in $REQUIRED_TABLES; do
    if [[ $TABLES != *"$table"* ]]; then
        echo "❌ Table '$table' missing."
        exit 1
    fi
done
echo "✅ All required tables exist."

echo "Step 3: Testing POST /events"
RESPONSE=$(curl -s -X POST "$API_URL/events" \
  -H "Content-Type: application/json" \
  -d '{"eventType": "TestEvent", "sourceAgent": "verify-script", "sessionId": "verify-1", "projectDir": "/tmp", "toolName": "test", "payload": null}')

if [[ $RESPONSE != *'"ok":true'* ]]; then
    echo "❌ Failed to post event: $RESPONSE"
    exit 1
fi
echo "✅ POST /events successful."

echo "Step 4: Testing Session Lifecycle"
SESSION_ID="verify-session-$(date +%s)"
curl -s -X POST "$API_URL/sessions/start" \
  -H "Content-Type: application/json" \
  -d "{\"sessionId\": \"$SESSION_ID\", \"sourceAgent\": \"verify-script\", \"projectDir\": \"/tmp\"}" > /dev/null

echo "Session started. Updating status to ended..."
curl -s -X POST "$API_URL/sessions/end" \
  -H "Content-Type: application/json" \
  -d "{\"sessionId\": \"$SESSION_ID\"}" > /dev/null

STATUS=$(sqlite3 "$DB_PATH" "SELECT status FROM sessions WHERE session_id = '$SESSION_ID'")
if [[ "$STATUS" == "ended" ]]; then
    echo "✅ Session status updated to 'ended' in DB."
else
    echo "❌ Session status is '$STATUS', expected 'ended'."
    exit 1
fi

echo "✅ All verification steps passed!"
