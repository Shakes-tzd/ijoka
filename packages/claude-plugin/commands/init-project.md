# /init-project

Initialize a new project with `feature_list.json` for structured task management.

## What This Command Does

Creates a `feature_list.json` file in the current project directory following Anthropic's long-running agent pattern. This file serves as a persistent task queue that survives across sessions.

## Usage

Run `/init-project` and provide:
1. Project name/description
2. Initial features to implement

## Example

User: `/init-project`

Claude will:
1. Ask about the project and its goals
2. Help define initial features with categories
3. Create `feature_list.json` with the structure:

```json
[
  {
    "category": "functional",
    "description": "User authentication with OAuth",
    "steps": ["Create auth route", "Implement OAuth flow", "Add session management"],
    "passes": false
  },
  {
    "category": "ui",
    "description": "Responsive navigation component",
    "steps": ["Create Nav component", "Add mobile menu", "Test responsiveness"],
    "passes": false
  }
]
```

## Feature Categories

- **functional** - Core functionality
- **ui** - User interface components
- **security** - Security features
- **performance** - Performance optimizations
- **documentation** - Documentation tasks
- **testing** - Test coverage
- **infrastructure** - DevOps/infrastructure
- **refactoring** - Code improvements

## Workflow After Initialization

1. At each session start, read `feature_list.json`
2. Pick ONE feature where `passes: false`
3. Implement and test thoroughly
4. Update ONLY `passes: false → true` when complete
5. Never remove or edit existing features

## Instructions for Claude

When the user runs this command:

1. Ask what project they're working on and its main goals
2. Help them identify 5-10 initial features to implement
3. For each feature, determine the appropriate category
4. Write clear, actionable descriptions
5. Add verification steps for each feature
6. Create the `feature_list.json` file in the project root
7. Explain the workflow for using the feature list
