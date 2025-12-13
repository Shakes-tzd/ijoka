/**
 * Configuration for Ijoka MCP Server
 */

import { z } from 'zod';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { execSync } from 'child_process';

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
 * Get the git repository root from a given path.
 *
 * In Ijoka, a PROJECT is defined by its git repository root. All subdirectories
 * within a git repo belong to the same project. This ensures consistent attribution
 * regardless of which subdirectory the MCP server is operating from.
 *
 * @param startPath - Starting directory to search from
 * @returns Git root path, or null if not in a git repo
 */
export function getGitRoot(startPath?: string): string | null {
  try {
    const cwd = startPath || process.cwd();
    const result = execSync('git rev-parse --show-toplevel', {
      cwd,
      encoding: 'utf-8',
      timeout: 5000,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    return result.trim();
  } catch {
    return null;
  }
}

/**
 * Get information about the current git worktree context.
 *
 * For parallel development, each worktree is treated as a separate workspace
 * but belongs to the same project (main repo).
 */
export function getWorktreeInfo(startPath?: string): {
  gitRoot: string | null;
  mainRepo: string | null;
  isWorktree: boolean;
  branch: string | null;
} {
  const info = {
    gitRoot: null as string | null,
    mainRepo: null as string | null,
    isWorktree: false,
    branch: null as string | null,
  };

  try {
    const cwd = startPath || process.cwd();

    // Get git root
    info.gitRoot = getGitRoot(cwd);

    // Get common dir (main repo .git directory)
    try {
      const commonDir = execSync('git rev-parse --git-common-dir', {
        cwd,
        encoding: 'utf-8',
        timeout: 5000,
        stdio: ['pipe', 'pipe', 'pipe'],
      }).trim();

      // If common dir doesn't end with .git, we're in a worktree
      if (!commonDir.endsWith('.git')) {
        const mainGitDir = path.resolve(commonDir);
        info.mainRepo = path.dirname(mainGitDir);
        info.isWorktree = true;
      } else {
        info.mainRepo = info.gitRoot;
      }
    } catch {
      info.mainRepo = info.gitRoot;
    }

    // Get current branch
    try {
      info.branch = execSync('git rev-parse --abbrev-ref HEAD', {
        cwd,
        encoding: 'utf-8',
        timeout: 5000,
        stdio: ['pipe', 'pipe', 'pipe'],
      }).trim();
    } catch {
      // Ignore branch detection failures
    }
  } catch {
    // Not in a git repo
  }

  return info;
}

/**
 * Get the canonical project path for attribution.
 *
 * In Ijoka, PROJECT = GIT REPOSITORY. All work within a git repo, regardless
 * of subdirectory, is attributed to the same project.
 *
 * Priority:
 * 1. Git root from provided path
 * 2. Git root from CLAUDE_PROJECT_DIR
 * 3. Git root from IJOKA_PROJECT_PATH
 * 4. Git root from cwd
 * 5. Fallback to cwd (for non-git projects)
 *
 * @param providedPath - Optional path provided by the MCP tool call
 */
export function getProjectPath(providedPath?: string): string {
  // Try provided path first
  if (providedPath) {
    const gitRoot = getGitRoot(providedPath);
    if (gitRoot) return gitRoot;
  }

  // Try CLAUDE_PROJECT_DIR
  const claudeProjectDir = process.env.CLAUDE_PROJECT_DIR;
  if (claudeProjectDir) {
    const gitRoot = getGitRoot(claudeProjectDir);
    if (gitRoot) return gitRoot;
  }

  // Try IJOKA_PROJECT_PATH
  const ijokaProjectPath = process.env.IJOKA_PROJECT_PATH;
  if (ijokaProjectPath) {
    const gitRoot = getGitRoot(ijokaProjectPath);
    if (gitRoot) return gitRoot;
  }

  // Try cwd
  const gitRoot = getGitRoot();
  if (gitRoot) return gitRoot;

  // Fallback to cwd (non-git project)
  return providedPath || claudeProjectDir || ijokaProjectPath || process.cwd();
}

/**
 * Check if a path is inside a git repository.
 */
export function isGitInitialized(startPath?: string): boolean {
  return getGitRoot(startPath) !== null;
}
