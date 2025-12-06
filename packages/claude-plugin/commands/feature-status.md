# /feature-status

Show the current status of all features in `feature_list.json`.

## What This Command Does

Reads `feature_list.json` and displays:
- Overall completion percentage
- Features by status (To Do, In Progress, Done)
- Features grouped by category
- Next recommended feature to work on

## Usage

Simply run `/feature-status` in any project with a `feature_list.json` file.

## Example Output

```
## Project Status: 4/10 features complete (40%)

### ✅ Done (4)
- [functional] User authentication with OAuth
- [functional] Database schema and migrations
- [ui] Responsive navigation component
- [testing] Unit tests for auth module

### 🔄 In Progress (1)
- [functional] API rate limiting

### 📋 To Do (5)
- [security] Input validation and sanitization
- [ui] Dashboard layout
- [performance] Query optimization
- [documentation] API documentation
- [infrastructure] CI/CD pipeline

### Next Recommended
**[security] Input validation and sanitization**
Steps:
1. Add input validation middleware
2. Sanitize user inputs
3. Test against common attack vectors
```

## Instructions for Claude

When the user runs this command:

1. Read `feature_list.json` from the project root
2. If file doesn't exist, suggest running `/init-project`
3. Calculate statistics:
   - Total features
   - Completed (passes: true)
   - In progress (inProgress: true, passes: false)
   - To do (passes: false, inProgress: false or undefined)
4. Group features by status
5. Within each group, show category and description
6. Recommend the next feature to work on (first incomplete by category priority: security > functional > ui > others)
7. Show the steps for the recommended feature
