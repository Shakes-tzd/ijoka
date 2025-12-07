#!/bin/bash
echo "$(date): PostToolUse fired" >> /tmp/agentkanban-hook-test.log
cat  # consume stdin
echo '{"continue": true}'
