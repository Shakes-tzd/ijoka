# /add-feature

Add a new feature to the Ijoka graph database.

## Usage

```
/add-feature <category> <description>
```

**Categories:** functional, ui, security, performance, documentation, testing, infrastructure, refactoring, planning, meta

## Instructions

⚠️ **Note:** MCP server is deprecated. Use CLI commands when MCP tools are unavailable.

When this command is invoked:

1. **Parse the arguments** from: $ARGUMENTS
   - First word = category
   - Remaining words = description

2. **Validate category** - Must be one of:
   - functional, ui, security, performance, documentation
   - testing, infrastructure, refactoring, planning, meta

3. **Check for duplicates** - Use `ijoka_status` MCP tool OR `ijoka status` CLI
   - Use fuzzy matching on descriptions
   - If duplicate found, ask user to confirm or modify

4. **Create the feature** - Use `ijoka_create_feature` MCP tool OR CLI:
   ```bash
   # MCP tool
   ijoka_create_feature:
     description: "<description>"
     category: "<category>"
     priority: 50  # Default priority, can be specified

   # OR CLI
   ijoka feature create --category "<category>" --priority 50 "<description>"
   ```

5. **Confirm creation** - Show:
   - Feature created successfully
   - Current feature count
   - Suggest `/next-feature` if no active feature

## Validation Rules

- Category must be valid (see list above)
- Description must be non-empty
- Description should be unique (warn on similar features)

## Examples

```
/add-feature functional User can export data to CSV format
```

Creates feature:
- description: "User can export data to CSV format"
- category: "functional"
- priority: 50

```
/add-feature security Implement rate limiting on API endpoints
```

Creates feature:
- description: "Implement rate limiting on API endpoints"
- category: "security"
- priority: 50

## Advanced Usage

To specify priority, include it after category:

```
/add-feature security:90 Implement rate limiting
```

This creates the feature with priority 90 (higher = more urgent).
