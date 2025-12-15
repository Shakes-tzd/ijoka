# /init-project

Initialize a new project in the Ijoka graph database for structured task management.

## What This Command Does

Registers the current project in Ijoka's Memgraph database and helps you define initial features. Projects are identified by their **git repository root** - all subdirectories within a git repo belong to the same project.

## Prerequisites

Before running this command, ensure:
1. **Memgraph is running**: `docker compose up -d` (from ijoka repo)
2. **Ijoka CLI is installed**: `ijoka --version` should work
3. **uv is installed**: `uv --version` should show 0.8.0+ for full Python support

## Usage

Run `/init-project` and provide:
1. Project name/description
2. Initial features to implement

## Example

User: `/init-project`

Claude will:
1. Check uv installation and version
2. Check if directory is a git repository (initialize if not)
3. Detect existing agent config files (CLAUDE.md, GEMINI.md, etc.)
4. Offer to add Python standards to config files
5. Verify Memgraph connectivity via `ijoka status`
6. Ask about the project and its goals
7. Help define initial features with categories
8. Create features using `ijoka feature create`
9. Explain the workflow for using Ijoka

## Feature Categories

- **functional** - Core functionality
- **ui** - User interface components
- **security** - Security features
- **performance** - Performance optimizations
- **documentation** - Documentation tasks
- **testing** - Test coverage
- **infrastructure** - DevOps/infrastructure
- **refactoring** - Code improvements
- **planning** - Research, design, discovery work
- **meta** - Tooling, observability, workflow improvements

## Workflow After Initialization

1. At session start, run `/ijoka:start` or `ijoka status` CLI
2. Use `ijoka feature start <ID>` CLI to begin work (or `/next-feature`)
3. Work on ONE feature at a time
4. Use `ijoka feature complete` CLI when done (or `/complete-feature`)
5. Use `ijoka plan set` CLI to declare implementation steps

## Instructions for Claude

When the user runs this command:

### Step 1: Validate Environment

**Check uv installation:**
```bash
uv --version
```

- If uv is not installed, inform user: "Ijoka requires uv for Python execution. Install with: `curl -LsSf https://astral.sh/uv/install.sh | sh`"
- If uv version is below 0.8.0, suggest upgrade: "uv 0.8.0+ recommended for full PEP 723 support. Upgrade with: `pip install --upgrade uv`"
- Explain: "uv ensures reproducible Python environments. See PYTHON_STANDARDS.md for details."

### Step 2: Ensure Git Repository

**IMPORTANT**: In Ijoka, a project is defined by its git repository root. All work attribution depends on git.

1. **Check git status** - Run `git rev-parse --show-toplevel` to find the git root
2. **If not in a git repo** - Ask the user if they want to initialize one:
   - Explain: "Ijoka uses git to identify projects. All work in subdirectories is attributed to the same project."
   - If user agrees, run `git init` and create an initial commit
   - Suggest creating a `.gitignore` file with common patterns
3. **If in a git repo** - Note the git root path for project registration

### Step 3: Detect Agent Config Files

Search for existing AI agent configuration files in the project root:

**Known config files:**
- `CLAUDE.md` / `claude.md` / `.claude.md` - Claude Code
- `GEMINI.md` / `gemini.md` / `.gemini.md` - Google Gemini
- `CURSOR.md` / `cursor.md` / `.cursorrules` - Cursor IDE
- `COPILOT.md` / `copilot.md` - GitHub Copilot
- `AGENT.md` / `agent.md` / `AI.md` - Generic agent configs

For each config file found:
1. Check if it already has a Python section (search for "Python", "uv run", "PYTHON_STANDARDS")
2. Report: "Found {filename} - Python section: {yes/no}"

### Step 4: Offer Python Standards Integration

**Ask the user:**

> "I found the following agent config files:
> - CLAUDE.md (Python section: yes/no)
> - GEMINI.md (Python section: yes/no)
>
> Ijoka uses uv for reproducible Python execution. Would you like me to add Python standards to config files that don't have them?
>
> This ensures all AI agents (Claude, Gemini, Cursor, etc.) follow the same Python execution rules."

If user agrees, add the following section to each config file missing Python standards:

```markdown
### Python (CRITICAL)

**See Ijoka's `PYTHON_STANDARDS.md` for full details.**

Key rules:
- **ALWAYS use `uv run` to execute Python scripts** - never `python3` directly
- Scripts with dependencies MUST have uv shebang: `#!/usr/bin/env -S uv run --script`

```bash
# ✅ CORRECT
uv run script.py

# ❌ WRONG - will fail with missing dependencies
python3 script.py
```
```

### Step 5: Check Connectivity

- Run `ijoka status` to verify Memgraph is running
- If connection fails, inform user to start Memgraph: `docker compose up -d`

### Step 6: Gather Project Info

- Ask what project they're working on and its main goals
- Note: The project path will be the git root, not the current directory

### Step 7: Define Features

Help identify 5-10 initial features:
- For each feature, determine the appropriate category
- Write clear, actionable descriptions
- Add verification steps for each feature

### Step 8: Create Features

For each feature:
```bash
ijoka feature create --category "functional" --priority 100 "Feature description"
```
Decrease priority by 10 for each subsequent feature.

### Step 9: Confirm Setup

Show the created features and explain:
- Use `/ijoka:start` at session start
- Use `/next-feature` to pick up work
- Use `/complete-feature` when done
- All activity is automatically tracked in the graph database
- Work in any subdirectory will be attributed to this project
- All AI agents will follow the same Python standards

## Migration from feature_list.json

If the project has an existing `feature_list.json` file, suggest running `/migrate` to import those features into the graph database.

## Project Identity

Remember: **PROJECT = GIT REPOSITORY**

- All subdirectories within a git repo are part of the same project
- Git worktrees are recognized as separate workspaces of the same project
- The git root path is stored in Memgraph as the project identifier
- Python standards apply to ALL AI agents working on the project
