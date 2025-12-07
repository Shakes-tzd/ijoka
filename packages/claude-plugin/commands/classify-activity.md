# Classify Recent Activity

Spawn a Haiku subagent to intelligently classify recent activity and link it to the correct features.

## Instructions

Use the Task tool to spawn a Haiku agent that will:

1. Read the project's `feature_list.json` to get available features
2. Query AgentKanban for recent unlinked events (last 20 events without feature_id)
3. For each unlinked event, determine the best matching feature based on:
   - Tool name and input (file paths, commands, patterns)
   - Semantic meaning of the work being done
   - Feature descriptions and steps
4. Update the feature links via the AgentKanban API

```
Task tool parameters:
- subagent_type: "general-purpose"
- model: "haiku"
- prompt: |
    You are a feature classifier for the AgentKanban observability system.

    Your task:
    1. Read feature_list.json from the current project directory
    2. Fetch recent events from http://127.0.0.1:4000/events?limit=20&unlinked=true
    3. For each event, analyze the tool_name and payload to determine which feature it relates to
    4. Update the event's feature_id via POST http://127.0.0.1:4000/events/{id}/link

    Classification rules:
    - Match based on semantic meaning, not just keywords
    - File paths indicate which part of codebase is being modified
    - Bash commands reveal intent (build, test, deploy, etc.)
    - Edit/Write operations show what's being changed
    - If no good match (< 30% confidence), leave unlinked

    After classification, report:
    - How many events were classified
    - Which features they were linked to
    - Any events that couldn't be matched
```

Execute this task now.
