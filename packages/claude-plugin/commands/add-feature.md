# Add Feature Command

Add a new feature to feature_list.json in a deterministic, validated way.

## Usage

```
/add-feature <category> <description>
```

**Categories:** infrastructure, functional, ui, documentation, testing, security

## Instructions

When this command is invoked:

1. **Parse the arguments** from: $ARGUMENTS

2. **Validate the feature_list.json exists** in the current project directory. If not, create it with an empty array.

3. **Check for duplicates** - ensure no existing feature has the same description (case-insensitive).

4. **Add the new feature** with this exact structure:
   ```json
   {
     "category": "<category>",
     "description": "<description>",
     "steps": [],
     "passes": false,
     "inProgress": false
   }
   ```

5. **Preserve existing features** - append to the array, never modify existing entries.

6. **Write the file** with proper JSON formatting (2-space indent).

7. **Report success** with the new feature count.

## Validation Rules

- Category must be one of: infrastructure, functional, ui, documentation, testing, security
- Description must be non-empty and unique
- Never modify existing features
- Always maintain valid JSON structure

## Example

```
/add-feature functional User can export data to CSV format
```

Creates:
```json
{
  "category": "functional",
  "description": "User can export data to CSV format",
  "steps": [],
  "passes": false,
  "inProgress": false
}
```
