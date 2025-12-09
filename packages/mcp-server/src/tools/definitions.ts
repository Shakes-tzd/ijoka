/**
 * MCP Tool Definitions
 *
 * Defines the schema for all Ijoka tools.
 * These definitions are sent to the client on ListTools request.
 */

import type { Tool } from '@modelcontextprotocol/sdk/types.js';

export const toolDefinitions: Tool[] = [
  // ==========================================================================
  // TIER 1: Always Available (~200 tokens)
  // ==========================================================================
  {
    name: 'ijoka_status',
    description: `Get current project status, active task, and context.
This is the primary read interface - returns comprehensive state in one call.
Use this to understand what you're working on and project progress.`,
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
      },
      required: ['description', 'category'],
    },
  },
];
