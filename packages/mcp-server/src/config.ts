/**
 * Configuration for Ijoka MCP Server
 */

import { z } from 'zod';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

const ConfigSchema = z.object({
  graphDbUri: z.string().default('bolt://localhost:7687'),
  graphDbUser: z.string().default('ijoka'),
  graphDbPassword: z.string().default('ijoka_dev'),
  graphDbDatabase: z.string().default('memgraph'),
  defaultProjectPath: z.string().optional(),
});

export type Config = z.infer<typeof ConfigSchema>;

/**
 * Load configuration from various sources (env vars, config file)
 */
export async function loadConfig(): Promise<Config> {
  // First, try environment variables
  const envConfig: Partial<Config> = {
    graphDbUri: process.env.IJOKA_GRAPH_URI,
    graphDbUser: process.env.IJOKA_GRAPH_USER,
    graphDbPassword: process.env.IJOKA_GRAPH_PASSWORD,
    graphDbDatabase: process.env.IJOKA_GRAPH_DATABASE,
    defaultProjectPath: process.env.IJOKA_PROJECT_PATH || process.cwd(),
  };

  // Try to load from config file
  const configPath = path.join(os.homedir(), '.ijoka', 'mcp-config.json');
  let fileConfig: Partial<Config> = {};

  if (fs.existsSync(configPath)) {
    try {
      const content = fs.readFileSync(configPath, 'utf-8');
      fileConfig = JSON.parse(content);
    } catch (e) {
      console.error('Failed to parse config file:', e);
    }
  }

  // Merge configs (env vars take precedence)
  const merged = {
    ...fileConfig,
    ...Object.fromEntries(
      Object.entries(envConfig).filter(([, v]) => v !== undefined)
    ),
  };

  return ConfigSchema.parse(merged);
}

/**
 * Get the project path from various sources
 */
export function getProjectPath(providedPath?: string): string {
  // Priority: provided path > env var > cwd
  return (
    providedPath ||
    process.env.CLAUDE_PROJECT_DIR ||
    process.env.IJOKA_PROJECT_PATH ||
    process.cwd()
  );
}
