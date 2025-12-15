# /feature-status

Show the current status of all features from the Ijoka graph database.

## What This Command Does

Queries Memgraph and displays:
- Overall completion percentage
- Features by status (To Do, In Progress, Done)
- Features grouped by category
- Next recommended feature to work on
- Plan progress for active feature (if any)

## Usage

Simply run `/feature-status` in any project connected to Ijoka.

## Example Output

```
## Project Status: 4/10 features complete (40%)

### In Progress (1)
- [functional] API rate limiting
  Plan: 2/4 steps complete

### Done (4)
- [functional] User authentication with OAuth
- [functional] Database schema and migrations
- [ui] Responsive navigation component
- [testing] Unit tests for auth module

### To Do (5)
- [security] Input validation and sanitization (priority: 90)
- [ui] Dashboard layout (priority: 80)
- [performance] Query optimization (priority: 70)
- [documentation] API documentation (priority: 60)
- [infrastructure] CI/CD pipeline (priority: 50)

### Next Recommended
**[security] Input validation and sanitization**
Steps:
1. Add input validation middleware
2. Sanitize user inputs
3. Test against common attack vectors
```

## Instructions for Claude

When the user runs this command:

1. **Get project status** - Run `ijoka status`

2. **Handle connection errors** - If Memgraph is not running:
   - Inform user: "Memgraph is not running. Start it with: `docker compose up -d`"
   - Suggest running `/init-project` after starting Memgraph

3. **Format the response**:
   - Show overall progress (completed/total, percentage)
   - Group features by status:
     - **In Progress** - Currently being worked on (show plan progress if available)
     - **Done** - Completed features
     - **To Do** - Pending features (sorted by priority)
     - **Blocked** - Features that are blocked (if any)
   - Show category tag for each feature
   - Recommend next feature based on priority

4. **If active feature has a plan** - Run `ijoka plan show`

5. **Suggest actions**:
   - If no active feature: "Run `/next-feature` to start working"
   - If feature in progress: "Continue with current feature or `/complete-feature` when done"
   - If all done: "All features complete! Add more with `/add-feature`"
