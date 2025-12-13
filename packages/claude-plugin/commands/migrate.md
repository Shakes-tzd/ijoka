# Migrate feature_list.json to Graph Database

You are helping migrate features from the legacy `feature_list.json` file to the Ijoka graph database.

⚠️ **Note:** MCP server is deprecated. Use CLI commands when MCP tools are unavailable.

## Instructions

1. **Check for feature_list.json** in the current project directory
2. **Read the JSON file** and parse all features
3. **For each feature**, use `ijoka_create_feature` MCP tool OR CLI:
   - `description`: The feature description
   - `category`: The category (functional, ui, security, etc.)
   - `steps`: The verification steps array
   - `priority`: Assign based on position (first = highest priority)

   ```bash
   # CLI command
   ijoka feature create --category "<category>" --priority <N> "<description>"
   ```
4. **Report migration results** showing how many features were migrated
5. **Rename the file** to `feature_list.json.migrated` to prevent re-migration
6. **Do NOT delete** the original file - keep it as backup

## Example

If feature_list.json contains:
```json
[
  {"category": "functional", "description": "User authentication", "steps": ["Test login"], "passes": false},
  {"category": "ui", "description": "Dashboard layout", "steps": ["Check responsive"], "passes": true}
]
```

Call:
1. `ijoka_create_feature` with description="User authentication", category="functional", steps=["Test login"], priority=100
2. `ijoka_create_feature` with description="Dashboard layout", category="ui", steps=["Check responsive"], priority=90

Then report: "Migrated 2 features to graph database."

## Important Notes

- Features with `passes: true` should be completed after creation (`ijoka feature complete` CLI OR `ijoka_complete_feature` MCP)
- Features with `inProgress: true` should be started (`ijoka feature start <ID>` CLI OR `ijoka_start_feature` MCP)
- Priority decreases by 10 for each feature (100, 90, 80, ...)
- If no feature_list.json exists, inform the user that migration is not needed
