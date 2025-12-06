# /next-feature

Start working on the next incomplete feature from `feature_list.json`.

## What This Command Does

1. Reads `feature_list.json`
2. Finds the first feature where `passes: false`
3. Sets `inProgress: true` on that feature
4. Displays the feature details and steps
5. Begins implementation

## Usage

Run `/next-feature` to automatically pick up the next task.

Optionally specify a category: `/next-feature security`

## Example

User: `/next-feature`

Claude will:
1. Find: `{"description": "Input validation", "passes": false}`
2. Update: `{"description": "Input validation", "passes": false, "inProgress": true}`
3. Display the feature and its verification steps
4. Begin implementation

## Priority Order

When no category is specified, features are prioritized:
1. **security** - Security vulnerabilities first
2. **functional** - Core functionality
3. **testing** - Test coverage
4. **ui** - User interface
5. **performance** - Optimizations
6. **documentation** - Docs
7. **infrastructure** - DevOps
8. **refactoring** - Code cleanup

## Instructions for Claude

When the user runs this command:

1. Read `feature_list.json` from project root
2. If file doesn't exist, suggest `/init-project`
3. Find the first incomplete feature (passes: false)
   - If category specified, filter to that category
   - Otherwise, use priority order above
4. If all features complete, congratulate and suggest adding more
5. Update the feature to set `inProgress: true`
6. Display:
   - Feature description
   - Category
   - Verification steps
7. Begin implementing the feature
8. Work through each verification step
9. When complete, update `passes: true` and `inProgress: false`

## Important Rules

- Only work on ONE feature at a time
- Complete each step before moving on
- Test thoroughly before marking as complete
- NEVER remove or modify existing feature descriptions
- ONLY change `passes` and `inProgress` fields
