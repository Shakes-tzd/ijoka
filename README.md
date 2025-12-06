# 🎯 AgentKanban

**Unified observability and task management for AI coding agents.**

AgentKanban provides a lightweight desktop application and Claude Code plugin that implements [Anthropic's long-running agent pattern](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) for coordinating work across multiple AI coding assistants.

![AgentKanban Screenshot](docs/screenshot.png)

## Features

- 🖥️ **Desktop App** — Lightweight Tauri app with system tray, native notifications
- 📋 **Kanban Board** — Visual task management (To Do → In Progress → Done)  
- 🔄 **Real-time Sync** — Watch `feature_list.json` and session transcripts
- 🤖 **Multi-Agent Support** — Claude Code, Codex CLI, Gemini CLI
- 🔌 **Claude Plugin** — Hooks, commands, and agents for seamless integration
- 📊 **Activity Timeline** — Track what each agent is doing
- 🔔 **Notifications** — Native OS alerts on feature completion

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              AgentKanban Desktop (Tauri)                    │
│  - Kanban Board UI                                          │
│  - Activity Timeline                                        │
│  - Progress Stats                                           │
└─────────────────────────────────────────────────────────────┘
                          ▲ 
           SQLite + File Watcher + HTTP Server
                          │
    ┌─────────────────────┼─────────────────────┐
    │                     │                     │
┌───┴───┐            ┌────┴────┐           ┌────┴────┐
│ Claude │            │  Codex  │           │ Gemini  │
│ Code   │            │  CLI    │           │  CLI    │
└────────┘            └─────────┘           └─────────┘
    │                     │                     │
    └─────────────────────┴─────────────────────┘
                          │
                  feature_list.json
```

## Quick Start

### Prerequisites

- [Node.js](https://nodejs.org/) 20+
- [pnpm](https://pnpm.io/) 9+
- [Rust](https://rustup.rs/) 1.75+
- [Claude Code](https://claude.ai/code) (for plugin)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/agentkanban.git
cd agentkanban

# Install dependencies
pnpm install

# Run desktop app in development
pnpm dev

# Build for production
pnpm build
```

### Install Claude Plugin

```bash
# From the repo root
pnpm plugin:install

# Or manually
cd packages/claude-plugin
claude /plugin install .
```

## Project Structure

```
agentkanban/
├── apps/
│   └── desktop/              # Tauri desktop application
│       ├── src-tauri/        # Rust backend
│       │   ├── src/
│       │   │   ├── main.rs
│       │   │   ├── db.rs     # SQLite database
│       │   │   ├── watcher.rs # File watching
│       │   │   ├── server.rs  # HTTP server for hooks
│       │   │   └── commands.rs # Tauri commands
│       │   └── Cargo.toml
│       └── src/              # Vue frontend
│           ├── App.vue
│           └── components/
├── packages/
│   └── claude-plugin/        # Claude Code plugin
│       ├── .claude-plugin/
│       │   └── plugin.json
│       ├── hooks/
│       │   ├── hooks.json
│       │   └── scripts/
│       ├── commands/
│       ├── agents/
│       └── skills/
├── shared/
│   └── types/                # Shared TypeScript types
└── docs/                     # Documentation
```

## The Long-Running Agent Pattern

AgentKanban implements Anthropic's recommended pattern for multi-session development:

### `feature_list.json`

A persistent task queue that survives across sessions:

```json
[
  {
    "category": "functional",
    "description": "User authentication with OAuth",
    "steps": ["Create auth route", "Implement OAuth flow", "Add session management"],
    "passes": false
  }
]
```

### Agent Workflow

1. **SessionStart**: Agent reads `feature_list.json`, picks ONE feature where `passes: false`
2. **Implement**: Agent works on the feature, commits incrementally
3. **Complete**: Agent updates ONLY `passes: false → true`
4. **SessionEnd**: Clean state, no broken code

### Why JSON Not Markdown?

> "We use strongly-worded instructions like 'It is unacceptable to remove or edit tests.' After experimentation, we landed on JSON as the model is less likely to inappropriately change or overwrite JSON files compared to Markdown." — Anthropic

## Plugin Commands

| Command | Description |
|---------|-------------|
| `/init-project` | Initialize feature_list.json in current project |
| `/feature-status` | Show completion percentage and next tasks |
| `/next-feature` | Pick and start the next incomplete feature |

## Configuration

### Desktop App

Settings are stored in:
- **macOS**: `~/Library/Application Support/com.agentkanban.app/`
- **Windows**: `%APPDATA%\com.agentkanban.app\`
- **Linux**: `~/.config/com.agentkanban.app/`

### Plugin

Configure watched projects in `.claude/settings.json`:

```json
{
  "agentkanban": {
    "watchedProjects": [
      "/path/to/project1",
      "/path/to/project2"
    ],
    "syncServerPort": 4000
  }
}
```

## Development

```bash
# Run desktop app in dev mode
pnpm desktop:dev

# Build desktop app
pnpm desktop:build

# Type check all packages
pnpm typecheck
```

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) first.

## License

MIT © Shakes

---

Built with ❤️ using [Tauri](https://tauri.app), [Vue](https://vuejs.org), and [Claude](https://claude.ai)
