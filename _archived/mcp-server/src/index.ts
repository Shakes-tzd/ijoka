#!/usr/bin/env node
/**
 * Ijoka MCP Server
 *
 * @deprecated This MCP server is DEPRECATED. Use the Ijoka CLI or REST API instead.
 *
 * MIGRATION GUIDE:
 * - CLI: `ijoka status`, `ijoka feature list`, `ijoka feature start <ID>`, etc.
 * - REST API: Start with `ijoka-server`, then use http://localhost:8000
 *
 * The CLI and REST API provide the same functionality with better validation,
 * audit trails, and work across all AI clients.
 *
 * ---
 *
 * Model Context Protocol server for AI agent integration.
 * Provides tools for agents to read/write project state.
 *
 * Transport: stdio (standard for MCP)
 *
 * Usage:
 *   npx @ijoka/mcp-server
 *
 * Configuration (Claude Code):
 *   Add to ~/.claude/settings.json:
 *   {
 *     "mcpServers": {
 *       "ijoka": {
 *         "command": "npx",
 *         "args": ["@ijoka/mcp-server"]
 *       }
 *     }
 *   }
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';

import { initGraphDB, closeGraphDB, isConnected } from './db.js';
import { toolDefinitions, handleToolCall } from './tools/index.js';
import { loadConfig } from './config.js';

const server = new Server(
  {
    name: 'ijoka',
    version: '0.1.0',
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// List available tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: toolDefinitions,
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  // Check database connection
  if (!isConnected()) {
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            success: false,
            error: 'Graph database not connected. Is Memgraph running?',
          }),
        },
      ],
      isError: true,
    };
  }

  try {
    const result = await handleToolCall(name, args || {});
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify(result, null, 2),
        },
      ],
    };
  } catch (error) {
    console.error(`[ijoka-mcp] Error in tool ${name}:`, error);
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            success: false,
            error: error instanceof Error ? error.message : 'Unknown error',
          }),
        },
      ],
      isError: true,
    };
  }
});

// Main entry point
async function main() {
  console.error('[ijoka-mcp] ⚠️  DEPRECATION WARNING: This MCP server is deprecated.');
  console.error('[ijoka-mcp] Please migrate to the Ijoka CLI or REST API:');
  console.error('[ijoka-mcp]   - CLI: ijoka status, ijoka feature list, etc.');
  console.error('[ijoka-mcp]   - API: ijoka-server (http://localhost:8000)');
  console.error('[ijoka-mcp]');
  console.error('[ijoka-mcp] Starting Ijoka MCP Server...');

  const config = await loadConfig();

  // Initialize graph database connection
  try {
    await initGraphDB({
      uri: config.graphDbUri,
      user: config.graphDbUser,
      password: config.graphDbPassword,
      database: config.graphDbDatabase,
    });
  } catch (error) {
    console.error('[ijoka-mcp] Failed to connect to graph database:', error);
    console.error('[ijoka-mcp] Tools will return errors until database is available.');
    // Continue anyway - tools will report connection errors
  }

  // Start MCP server
  const transport = new StdioServerTransport();
  await server.connect(transport);

  console.error('[ijoka-mcp] Server started, listening on stdio');

  // Cleanup on exit
  process.on('SIGINT', async () => {
    console.error('[ijoka-mcp] Shutting down...');
    await closeGraphDB();
    process.exit(0);
  });

  process.on('SIGTERM', async () => {
    console.error('[ijoka-mcp] Shutting down...');
    await closeGraphDB();
    process.exit(0);
  });
}

main().catch((error) => {
  console.error('[ijoka-mcp] Fatal error:', error);
  process.exit(1);
});
