# Update AgentKanban Plugin

Run the following commands sequentially to update the AgentKanban plugin to the latest version:

```bash
claude plugin marketplace update agentkanban
```

Wait for the marketplace update to complete, then:

```bash
claude plugin uninstall agentkanban@agentkanban
```

Wait for uninstall to complete, then:

```bash
claude plugin install agentkanban@agentkanban
```

**Important:** After running these commands, you may need to restart Claude Code for changes to take full effect.

Run each command above in sequence using the Bash tool.
