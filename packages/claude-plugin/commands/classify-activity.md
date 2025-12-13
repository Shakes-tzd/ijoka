# /classify-activity

Spawn a Haiku subagent to intelligently classify recent unlinked activity and associate it with features.

## What This Command Does

Uses a cost-efficient Haiku agent to:
1. Query Memgraph for recent events without feature links
2. Get the list of all features from the project
3. Intelligently match events to features based on context
4. Update the graph to link events to their features

## When to Use

- When activities have been recorded without proper feature attribution
- After switching features mid-session
- To clean up historical data
- When the automatic classification in hooks didn't work

## Instructions

Use the Task tool to spawn a Haiku agent:

```
Task tool parameters:
- subagent_type: "general-purpose"
- model: "haiku"
- prompt: |
    You are a feature classifier for the Ijoka observability system.

    Your task:
    1. Call `ijoka_status` to get all features for this project
    2. Query the graph database for recent unlinked events:
       - Use graph_db_helper.py or the MCP server
       - Look for events where LINKED_TO relationship doesn't exist
    3. For each unlinked event, analyze:
       - tool_name: What tool was used (Edit, Write, Bash, etc.)
       - payload: File paths, commands, patterns
       - summary: Any description of what was done
    4. Match each event to the most relevant feature:
       - File paths indicate which part of codebase
       - Bash commands reveal intent (test, build, deploy)
       - Edit/Write operations show what's being changed
    5. Create LINKED_TO relationships in the graph

    Classification rules:
    - Match based on semantic meaning, not just keywords
    - Consider the feature's category and description
    - If confidence < 30%, leave unlinked (don't guess)
    - Prefer active feature for ambiguous cases

    After classification, report:
    - How many events were classified
    - Which features they were linked to
    - Any events that couldn't be matched
```

Execute this task now.

## How Classification Works

The classifier analyzes events based on:

| Signal | What It Indicates |
|--------|-------------------|
| File paths in Edit/Write | Which component/feature area |
| `npm test`, `pytest` | Testing-related feature |
| `git commit` | Feature completion work |
| `docker`, `deploy` | Infrastructure feature |
| CSS/HTML changes | UI feature |
| SQL/database files | Data/functional feature |

## Example Output

```
## Classification Results

Classified 15 events:

### User Authentication (5 events)
- Edit: src/auth/login.ts
- Edit: src/auth/oauth.ts
- Write: src/auth/providers/google.ts
- Bash: npm test src/auth
- Bash: git commit -m "Add OAuth"

### Dashboard Layout (3 events)
- Edit: src/components/Dashboard.vue
- Edit: src/styles/dashboard.css
- Write: src/components/Sidebar.vue

### Unlinked (2 events)
- Bash: npm install (ambiguous - could be any feature)
- Read: package.json (exploration, not specific)
```
