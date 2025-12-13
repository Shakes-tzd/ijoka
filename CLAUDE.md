# CLAUDE.md - Ijoka Development Guide

## Project Overview

**Ijoka** (Zulu for "yoke") is a unified observability and orchestration system for AI coding agents. It implements [Anthropic's long-running agent pattern](https://www.anthropic.com/engineering/claude-code-best-practices) with a Tauri desktop app and Claude Code plugin - yoking AI agents together for coordinated work.

## Architecture

```
ijoka/
├── apps/desktop/          # Tauri app (Rust + Vue 3)
│   ├── src-tauri/         # Rust backend
│   │   ├── src/
│   │   │   ├── main.rs    # App entry, tray, setup
│   │   │   ├── db.rs      # SQLite operations
│   │   │   ├── watcher.rs # File watching
│   │   │   ├── server.rs  # HTTP server (port 4000)
│   │   │   └── commands.rs # Tauri commands
│   │   └── Cargo.toml
│   └── src/               # Vue 3 frontend
│       ├── App.vue
│       └── components/
├── packages/claude-plugin/ # Claude Code plugin
│   ├── hooks/             # SessionStart, SessionEnd, PostToolUse
│   ├── commands/          # /init-project, /feature-status, /next-feature
│   └── skills/            # Feature workflow guidance
└── shared/types/          # Shared TypeScript types
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Desktop Framework | Tauri 2.x |
| Backend | Rust (rusqlite, axum, notify, tokio) |
| Frontend | Vue 3 + TypeScript + Vite |
| Graph Database | Memgraph (source of truth) |
| Local Cache | SQLite (embedded, synced from graph) |
| CLI/SDK | Python (packages/ijoka-cli) - `ijoka` command |
| REST API | FastAPI on port 8000 |
| Plugin | Claude Code hooks/commands/skills |

## Development Commands

```bash
# Install dependencies
pnpm install

# Run desktop app in dev mode
pnpm dev

# Build for production
pnpm build

# Install Claude plugin locally
cd packages/claude-plugin && claude /plugin install .
```

## Key Files to Understand

### Rust Backend (apps/desktop/src-tauri/src/)

- **main.rs** - App initialization, system tray, event broadcasting
- **db.rs** - SQLite schema and CRUD operations for events, features, sessions
- **watcher.rs** - File watcher for `feature_list.json` and transcripts
- **server.rs** - Axum HTTP server receiving hook events on port 4000
- **commands.rs** - Tauri commands exposed to frontend

### Vue Frontend (apps/desktop/src/)

- **App.vue** - Main layout, data loading, real-time event listeners
- **KanbanBoard.vue** - Three-column kanban layout
- **KanbanColumn.vue** - Individual column with feature cards
- **ActivityTimeline.vue** - Real-time event feed
- **StatsBar.vue** - Progress statistics display

### Plugin (packages/claude-plugin/)

- **hooks/hooks.json** - Hook configuration
- **hooks/scripts/** - Shell/Python scripts for hooks
- **commands/** - Slash command definitions
- **skills/** - SKILL.md for feature workflow

## Data Architecture

**Single Source of Truth: Memgraph (Graph Database)**

```
┌─────────────────────────────────────────────────────────────────┐
│                    IJOKA DATA ARCHITECTURE                       │
│                                                                  │
│                    ┌──────────────────┐                          │
│                    │   MEMGRAPH       │ ◄── SOURCE OF TRUTH      │
│                    │   (Graph DB)     │     bolt://localhost:7687│
│                    │                  │                          │
│                    │  • Features      │                          │
│                    │  • Sessions      │                          │
│                    │  • Events        │                          │
│                    │  • StatusEvents  │                          │
│                    └────────┬─────────┘                          │
│                             │                                    │
│         ┌───────────────────┼───────────────────┐                │
│         │                   │                   │                │
│         ▼                   ▼                   ▼                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ SQLite       │    │  Tauri UI    │    │  ijoka CLI   │       │
│  │ (local cache)│    │  (reads DB)  │    │  & REST API  │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                                  │
│  ⚠️ feature_list.json is DEPRECATED - do not use               │
│  ⚠️ MCP Server is DEPRECATED - use CLI/API instead             │
└─────────────────────────────────────────────────────────────────┘
```

**Feature Management via CLI:**
```bash
ijoka status                    # Get current project status and active feature
ijoka feature list              # List all features
ijoka feature start [ID]        # Start working on a feature
ijoka feature complete          # Mark current feature as complete
ijoka feature block --reason    # Mark feature as blocked
ijoka feature create            # Create a new feature
ijoka insight record            # Record a reusable insight
ijoka analytics digest          # Get daily insights digest
ijoka analytics ask "question"  # Natural language analytics query
```

**REST API (http://localhost:8000):**
- `GET /status` - Project status
- `GET /features` - List features
- `POST /features/{id}/start` - Start feature
- `POST /features/{id}/complete` - Complete feature
- `POST /analytics/query` - Natural language query

**Validation:**
```bash
# Run graph database validation
uv run packages/claude-plugin/hooks/scripts/graph_validator.py

# Auto-fix issues
uv run packages/claude-plugin/hooks/scripts/graph_validator.py --fix
```

## Code Style

### Python (CRITICAL)

**See `packages/claude-plugin/hooks/scripts/PYTHON_STANDARDS.md` for full details.**

Key rules:
- **ALWAYS use `uv run` to execute Python scripts** - never `python3` directly
- Scripts with dependencies MUST have uv shebang: `#!/usr/bin/env -S uv run --script`
- Git utilities are in `git_utils.py` (no deps) - import directly from there
- Database operations are in `graph_db_helper.py` (needs neo4j via uv)

```bash
# ✅ CORRECT
uv run script.py

# ❌ WRONG - will fail with missing dependencies
python3 script.py
```

### Rust
- Use `tracing` for logging
- Handle errors with `Result` types
- Keep database operations in `db.rs`
- Use Tauri's state management for shared data

### Vue/TypeScript
- Composition API with `<script setup>`
- Props with TypeScript interfaces
- CSS scoped to components
- Dark theme with CSS variables

### General
- Commits should be atomic and well-described
- Test changes before marking features complete
- Leave code in working state at session end

## Current Status

The scaffold is complete. Development priorities:

1. **Core Functionality** - Get Tauri app running with basic features
2. **Plugin Integration** - Test hooks sending events to app
3. **File Watching** - Verify feature_list.json changes sync
4. **UI Polish** - Improve kanban board interactions
5. **Multi-Agent** - Add Codex/Gemini adapters

## Useful Context

- HTTP server runs on `http://127.0.0.1:4000`
- Memgraph runs on `bolt://localhost:7687` (Docker)
- SQLite cache stored at `~/.ijoka/ijoka.db`
- Events broadcast to frontend via Tauri events

## When Starting a Session

1. Ensure Memgraph is running: `docker compose up -d`
2. Run `pnpm dev` to start the app
3. Run `ijoka status` to see current feature and progress
4. Work on the active feature
5. Run `ijoka feature complete` when done

**Optionally start the API server:**
```bash
ijoka-server  # Starts REST API on port 8000
```

## Infrastructure

```bash
# Start Memgraph
docker compose up -d

# Check Memgraph status
docker compose ps

# View Memgraph logs
docker compose logs memgraph
```
