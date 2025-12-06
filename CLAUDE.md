# CLAUDE.md - AgentKanban Development Guide

## Project Overview

**AgentKanban** is a unified observability and task management system for AI coding agents. It implements [Anthropic's long-running agent pattern](https://www.anthropic.com/engineering/claude-code-best-practices) with a Tauri desktop app and Claude Code plugin.

## Architecture

```
agentkanban/
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
| Database | SQLite (embedded) |
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

## Feature List Pattern

This project uses `feature_list.json` for task management:

```json
[
  {
    "category": "functional",
    "description": "What the feature does",
    "steps": ["How to verify it works"],
    "passes": false
  }
]
```

**Rules:**
1. Pick ONE feature where `passes: false`
2. Set `inProgress: true` while working
3. Complete and test thoroughly
4. Set `passes: true` when done
5. NEVER remove or edit existing features

## Code Style

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
- Database stored in app data directory
- File watcher monitors `~/.claude/projects` and configured project dirs
- Events broadcast to frontend via Tauri events

## When Starting a Session

1. Check `feature_list.json` for current progress
2. Run `pnpm dev` to start the app
3. Pick ONE incomplete feature to work on
4. Test thoroughly before marking complete
