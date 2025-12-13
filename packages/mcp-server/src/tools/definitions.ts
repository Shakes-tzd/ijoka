/**
 * MCP Tool Definitions
 *
 * Defines the schema for all Ijoka tools.
 * These definitions are sent to the client on ListTools request.
 *
 * IMPORTANT: These MCP tools are the ONLY interface for Ijoka operations.
 * Never bypass MCP by calling Python scripts or database queries directly.
 */

import type { Tool } from '@modelcontextprotocol/sdk/types.js';

/**
 * Enforcement notice included in primary tool description.
 * This ensures agents see the MCP-first mandate on every status check.
 */
const MCP_ENFORCEMENT = `

IMPORTANT: Always use ijoka_* MCP tools for ALL Ijoka operations.
Never bypass MCP by calling Python scripts, database queries, or internal APIs directly.
MCP tools provide validation, audit trails, and work across all AI clients (Claude, Cursor, Windsurf, etc).`;

export const toolDefinitions: Tool[] = [
  // ==========================================================================
  // TIER 1: Always Available (~200 tokens)
  // ==========================================================================
  {
    name: 'ijoka_status',
    description: `Get current project status, active features, and context.
This is the primary read interface - returns comprehensive state in one call.
Use this to understand what you're working on and project progress.${MCP_ENFORCEMENT}`,
    inputSchema: {
      type: 'object',
      properties: {
        include_insights: {
          type: 'boolean',
          description: 'Include relevant insights for current context',
        },
        include_blockers: {
          type: 'boolean',
          description: 'Include list of blocked features',
        },
        project_path: {
          type: 'string',
          description: 'Project path (defaults to current working directory)',
        },
        source_agent: {
          type: 'string',
          description: 'Agent identifier (e.g., claude-code, gemini-cli, codex-cli). Required for non-Claude tools.',
        },
        session_id: {
          type: 'string',
          description: 'Unique session identifier from the calling agent',
        },
      },
      required: [],
    },
  },

  // ==========================================================================
  // TIER 2: Feature Lifecycle (~300 tokens)
  // ==========================================================================
  {
    name: 'ijoka_start_feature',
    description: `Start working on a feature. Sets status to 'in_progress' and assigns you.
If no feature_id specified, starts the next available feature (highest priority pending).`,
    inputSchema: {
      type: 'object',
      properties: {
        feature_id: {
          type: 'string',
          description: 'Feature ID to start (uses next feature if not specified)',
        },
        agent: {
          type: 'string',
          description: 'Agent identifier (auto-detected if not provided)',
        },
        source_agent: {
          type: 'string',
          description: 'Agent identifier (e.g., claude-code, gemini-cli, codex-cli). Required for non-Claude tools.',
        },
        session_id: {
          type: 'string',
          description: 'Unique session identifier from the calling agent',
        },
      },
      required: [],
    },
  },
  {
    name: 'ijoka_complete_feature',
    description: `Mark a feature as complete. Records completion event and updates stats.`,
    inputSchema: {
      type: 'object',
      properties: {
        feature_id: {
          type: 'string',
          description: 'Feature ID to complete (uses current active if not specified)',
        },
        summary: {
          type: 'string',
          description: 'Brief summary of what was done',
        },
        commit_hash: {
          type: 'string',
          description: 'Git commit hash associated with completion',
        },
        source_agent: {
          type: 'string',
          description: 'Agent identifier (e.g., claude-code, gemini-cli, codex-cli). Required for non-Claude tools.',
        },
        session_id: {
          type: 'string',
          description: 'Unique session identifier from the calling agent',
        },
      },
      required: [],
    },
  },
  {
    name: 'ijoka_block_feature',
    description: `Report that work on a feature is blocked.`,
    inputSchema: {
      type: 'object',
      properties: {
        feature_id: {
          type: 'string',
          description: 'Feature ID (uses current active if not specified)',
        },
        reason: {
          type: 'string',
          description: 'Why the feature is blocked',
        },
        blocking_feature_id: {
          type: 'string',
          description: 'If blocked by another feature, its ID',
        },
        source_agent: {
          type: 'string',
          description: 'Agent identifier (e.g., claude-code, gemini-cli, codex-cli). Required for non-Claude tools.',
        },
        session_id: {
          type: 'string',
          description: 'Unique session identifier from the calling agent',
        },
      },
      required: ['reason'],
    },
  },

  // ==========================================================================
  // TIER 3: Learning & Insights (~400 tokens)
  // ==========================================================================
  {
    name: 'ijoka_record_insight',
    description: `Record a reusable insight or learning from current work.
These insights can be surfaced to future sessions working on similar tasks.`,
    inputSchema: {
      type: 'object',
      properties: {
        description: {
          type: 'string',
          description: 'What was learned',
        },
        pattern_type: {
          type: 'string',
          enum: ['solution', 'anti_pattern', 'best_practice', 'tool_usage'],
          description: 'Type of insight',
        },
        tags: {
          type: 'array',
          items: { type: 'string' },
          description: 'Tags for categorization and search',
        },
        feature_id: {
          type: 'string',
          description: 'Link to feature this insight came from',
        },
        source_agent: {
          type: 'string',
          description: 'Agent identifier (e.g., claude-code, gemini-cli, codex-cli). Required for non-Claude tools.',
        },
        session_id: {
          type: 'string',
          description: 'Unique session identifier from the calling agent',
        },
      },
      required: ['description', 'pattern_type'],
    },
  },
  {
    name: 'ijoka_get_insights',
    description: `Get relevant insights for current work or by search query.`,
    inputSchema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'Search query',
        },
        tags: {
          type: 'array',
          items: { type: 'string' },
          description: 'Filter by tags',
        },
        limit: {
          type: 'integer',
          description: 'Maximum insights to return (default: 5)',
        },
        source_agent: {
          type: 'string',
          description: 'Agent identifier (e.g., claude-code, gemini-cli, codex-cli). Required for non-Claude tools.',
        },
        session_id: {
          type: 'string',
          description: 'Unique session identifier from the calling agent',
        },
      },
      required: [],
    },
  },
  {
    name: 'ijoka_create_feature',
    description: `Create a new feature in the project.`,
    inputSchema: {
      type: 'object',
      properties: {
        description: {
          type: 'string',
          description: 'Feature description',
        },
        category: {
          type: 'string',
          enum: [
            'functional',
            'ui',
            'security',
            'performance',
            'documentation',
            'testing',
            'infrastructure',
            'refactoring',
            'planning',  // Knowledge acquisition: research, design, discovery, backlog alignment
            'meta',      // Process optimization: tooling, observability, workflow improvements
          ],
          description: 'Feature category',
        },
        steps: {
          type: 'array',
          items: { type: 'string' },
          description: 'Verification steps',
        },
        priority: {
          type: 'integer',
          description: 'Priority (higher = more important)',
        },
        branch_hint: {
          type: 'string',
          description: 'Git branch name associated with this feature (e.g., "feature/auth")',
        },
        file_patterns: {
          type: 'array',
          items: { type: 'string' },
          description: 'File path patterns for automatic classification (glob patterns, e.g., "src/auth/**", "tests/auth/**")',
        },
        source_agent: {
          type: 'string',
          description: 'Agent identifier (e.g., claude-code, gemini-cli, codex-cli). Required for non-Claude tools.',
        },
        session_id: {
          type: 'string',
          description: 'Unique session identifier from the calling agent',
        },
      },
      required: ['description', 'category'],
    },
  },

  // ==========================================================================
  // TIER 4: Plan Management (~300 tokens)
  // ==========================================================================
  {
    name: 'ijoka_set_plan',
    description: `Declare your implementation plan for the current feature. Creates Step nodes that track your progress.`,
    inputSchema: {
      type: 'object',
      properties: {
        steps: {
          type: 'array',
          items: { type: 'string' },
          description: 'Ordered list of implementation steps',
        },
        feature_id: {
          type: 'string',
          description: 'Feature ID to set plan for (uses active feature if not specified)',
        },
        project_path: {
          type: 'string',
          description: 'Project path (defaults to current working directory)',
        },
        source_agent: {
          type: 'string',
          description: 'Agent identifier (e.g., claude-code, gemini-cli, codex-cli). Required for non-Claude tools.',
        },
        session_id: {
          type: 'string',
          description: 'Unique session identifier from the calling agent',
        },
      },
      required: ['steps'],
    },
  },
  {
    name: 'ijoka_checkpoint',
    description: `Report progress and get feedback on current work. Returns any drift or stuckness warnings.`,
    inputSchema: {
      type: 'object',
      properties: {
        step_completed: {
          type: 'string',
          description: 'Description of step just completed (optional)',
        },
        current_activity: {
          type: 'string',
          description: 'What you are currently working on',
        },
        project_path: {
          type: 'string',
          description: 'Project path (defaults to current working directory)',
        },
        source_agent: {
          type: 'string',
          description: 'Agent identifier (e.g., claude-code, gemini-cli, codex-cli). Required for non-Claude tools.',
        },
        session_id: {
          type: 'string',
          description: 'Unique session identifier from the calling agent',
        },
      },
      required: [],
    },
  },
  {
    name: 'ijoka_get_plan',
    description: `Get the current plan status including all steps and their progress.`,
    inputSchema: {
      type: 'object',
      properties: {
        feature_id: {
          type: 'string',
          description: 'Feature ID to get plan for (uses active feature if not specified)',
        },
        project_path: {
          type: 'string',
          description: 'Project path (defaults to current working directory)',
        },
        source_agent: {
          type: 'string',
          description: 'Agent identifier (e.g., claude-code, gemini-cli, codex-cli). Required for non-Claude tools.',
        },
        session_id: {
          type: 'string',
          description: 'Unique session identifier from the calling agent',
        },
      },
      required: [],
    },
  },

  // ==========================================================================
  // TIER 5: On-Demand Feature Discovery (~400 tokens)
  // ==========================================================================
  {
    name: 'ijoka_discover_feature',
    description: `Create a new feature on-demand when you realize current work constitutes a distinct feature.
Use this when you identify that work you're doing (or just did) should be tracked as its own feature.
This tool:
1. Creates the feature
2. Sets it as active immediately
3. Re-attributes recent Session Work activities to the new feature (bidirectional linking)

WHEN TO USE:
- You realize mid-session that current work is a distinct feature
- User describes a new feature request during conversation
- You identify that recent work should be properly attributed

The feature will be linked to recent activities from the last N minutes (default: 60).`,
    inputSchema: {
      type: 'object',
      properties: {
        description: {
          type: 'string',
          description: 'Feature description',
        },
        category: {
          type: 'string',
          enum: [
            'functional',
            'ui',
            'security',
            'performance',
            'documentation',
            'testing',
            'infrastructure',
            'refactoring',
            'planning',
            'meta',
          ],
          description: 'Feature category',
        },
        steps: {
          type: 'array',
          items: { type: 'string' },
          description: 'Implementation/verification steps (optional)',
        },
        priority: {
          type: 'integer',
          description: 'Priority (higher = more important, default: 50)',
        },
        lookback_minutes: {
          type: 'integer',
          description: 'How many minutes back to look for activities to re-attribute (default: 60)',
        },
        mark_complete: {
          type: 'boolean',
          description: 'If true, mark the feature as complete immediately (for retroactive attribution of finished work)',
        },
        source_agent: {
          type: 'string',
          description: 'Agent identifier (e.g., claude-code, gemini-cli, codex-cli). Required for non-Claude tools.',
        },
        session_id: {
          type: 'string',
          description: 'Unique session identifier from the calling agent',
        },
      },
      required: ['description', 'category'],
    },
  },
];
