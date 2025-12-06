# GEMINI.md - AgentKanban Development Guide

## Project Overview

**AgentKanban** is a unified observability and task management system for AI coding agents. Built with Tauri (Rust + Vue), it provides a desktop kanban board that tracks work across multiple AI agents including Claude Code, Codex CLI, and Gemini CLI.

## Quick Reference

| What | Where |
|------|-------|
| Tauri Rust code | `apps/desktop/src-tauri/src/` |
| Vue frontend | `apps/desktop/src/` |
| Shared types | `shared/types/index.ts` |
| Claude plugin | `packages/claude-plugin/` |
| HTTP server port | `4000` |

## Architecture

```
┌─────────────────────────────────────────────────┐
│         AgentKanban Desktop (Tauri)             │
│  Kanban UI │ Activity Timeline │ Stats          │
└─────────────────────────────────────────────────┘
                       ▲
        SQLite + File Watcher + HTTP Server
                       │
       ┌───────────────┼───────────────┐
       │               │               │
   Claude Code    Codex CLI      Gemini CLI
       │               │               │
       └───────────────┴───────────────┘
                       │
               feature_list.json
```

## Development Setup

```bash
# Prerequisites: Node 20+, pnpm 9+, Rust 1.75+

# Install dependencies
pnpm install

# Run in development mode
pnpm dev

# Build for production
pnpm build
```

## Project Structure

```
agentkanban/
├── apps/desktop/
│   ├── src-tauri/           # Rust backend
│   │   ├── Cargo.toml       # Rust dependencies
│   │   ├── tauri.conf.json  # Tauri config
│   │   └── src/
│   │       ├── main.rs      # Entry point, tray, setup
│   │       ├── db.rs        # SQLite database
│   │       ├── watcher.rs   # File watching
│   │       ├── server.rs    # HTTP API (port 4000)
│   │       └── commands.rs  # Frontend commands
│   └── src/                 # Vue 3 frontend
│       ├── App.vue          # Main app
│       └── components/      # UI components
├── packages/claude-plugin/  # Claude Code integration
├── shared/types/            # TypeScript types
├── package.json             # pnpm workspace
└── pnpm-workspace.yaml
```

## Key Technologies

- **Tauri 2** - Desktop app framework (Rust + WebView)
- **Rust** - Backend (rusqlite, axum, notify, tokio)
- **Vue 3** - Frontend with Composition API
- **SQLite** - Embedded database
- **Axum** - HTTP server for receiving events

## Feature List Workflow

Tasks are tracked in `feature_list.json`:

```json
[
  {
    "category": "functional",
    "description": "Feature description",
    "steps": ["Verification steps"],
    "passes": false,
    "inProgress": false
  }
]
```

### Workflow Rules

1. Read `feature_list.json` at session start
2. Pick ONE feature where `passes: false`
3. Set `inProgress: true` while working
4. Implement and test thoroughly
5. Set `passes: true` when complete
6. **Never delete or modify feature descriptions**

## HTTP API (Port 4000)

The Tauri app runs an HTTP server for receiving events:

```bash
# Health check
GET http://127.0.0.1:4000/health

# Send event
POST http://127.0.0.1:4000/events
Content-Type: application/json
{
  "eventType": "ToolUse",
  "sourceAgent": "gemini-cli",
  "sessionId": "session-123",
  "projectDir": "/path/to/project",
  "toolName": "write_file"
}

# Feature update
POST http://127.0.0.1:4000/events/feature-update
Content-Type: application/json
{
  "projectDir": "/path/to/project",
  "stats": {"total": 10, "completed": 5, "percentage": 50},
  "changedFeatures": [{"description": "...", "category": "functional"}]
}

# Session lifecycle
POST http://127.0.0.1:4000/sessions/start
POST http://127.0.0.1:4000/sessions/end
```

## Database Schema

SQLite tables in `db.rs`:

```sql
-- Agent events
CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  event_type TEXT,
  source_agent TEXT,
  session_id TEXT,
  project_dir TEXT,
  tool_name TEXT,
  payload TEXT,
  created_at TEXT
);

-- Feature tracking
CREATE TABLE features (
  id TEXT PRIMARY KEY,
  project_dir TEXT,
  description TEXT,
  category TEXT,
  passes INTEGER,
  in_progress INTEGER,
  agent TEXT,
  updated_at TEXT
);

-- Active sessions
CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  source_agent TEXT,
  project_dir TEXT,
  started_at TEXT,
  last_activity TEXT,
  status TEXT
);
```

## Gemini CLI Integration

To integrate Gemini CLI with AgentKanban:

1. **Session Start** - POST to `/sessions/start`
2. **Tool Use** - POST to `/events` after each tool call
3. **Feature Complete** - POST to `/events/feature-update`
4. **Session End** - POST to `/sessions/end`

Example integration script:

```bash
#!/bin/bash
SYNC_SERVER="http://127.0.0.1:4000"

# Notify session start
curl -X POST "$SYNC_SERVER/sessions/start" \
  -H "Content-Type: application/json" \
  -d '{"sessionId": "'$SESSION_ID'", "sourceAgent": "gemini-cli", "projectDir": "'$PWD'"}'
```

## Code Style Guidelines

### Rust
- Use `Result` for error handling
- Log with `tracing::info!`, `tracing::error!`
- Keep modules focused (one concern per file)
- Use async/await with tokio

### Vue/TypeScript
- Composition API with `<script setup lang="ts">`
- Define props with TypeScript interfaces
- Scoped styles with CSS variables
- Reactive state with `ref()` and `computed()`

## Current Development Status

**Scaffold complete** - ready for implementation:

| Component | Status |
|-----------|--------|
| Rust backend | Scaffolded |
| Vue frontend | Scaffolded |
| Claude plugin | Scaffolded |
| Gemini adapter | TODO |
| Codex adapter | TODO |

## Session Checklist

When starting work:

- [ ] Check `feature_list.json` for progress
- [ ] Run `pnpm dev` to start the app
- [ ] Pick ONE incomplete feature
- [ ] Implement with tests
- [ ] Mark complete when done
- [ ] Commit with clear message
