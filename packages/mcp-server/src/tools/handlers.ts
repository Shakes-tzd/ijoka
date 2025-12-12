/**
 * MCP Tool Handlers
 *
 * Implements the logic for each Ijoka tool.
 */

import { getProjectPath } from '../config.js';
import * as db from '../db.js';

// Track MCP activities flag - can be disabled for debugging
const TRACK_ACTIVITIES = true;

export interface ToolResult {
  success: boolean;
  [key: string]: unknown;
}

/**
 * Handle a tool call by name
 */
export async function handleToolCall(
  name: string,
  args: Record<string, unknown>
): Promise<ToolResult> {
  let result: ToolResult;

  switch (name) {
    case 'ijoka_status':
      result = await handleStatus(args);
      break;
    case 'ijoka_start_feature':
      result = await handleStartFeature(args);
      break;
    case 'ijoka_complete_feature':
      result = await handleCompleteFeature(args);
      break;
    case 'ijoka_block_feature':
      result = await handleBlockFeature(args);
      break;
    case 'ijoka_record_insight':
      result = await handleRecordInsight(args);
      break;
    case 'ijoka_get_insights':
      result = await handleGetInsights(args);
      break;
    case 'ijoka_create_feature':
      result = await handleCreateFeature(args);
      break;
    case 'ijoka_set_plan':
      result = await handleSetPlan(args);
      break;
    case 'ijoka_checkpoint':
      result = await handleCheckpoint(args);
      break;
    case 'ijoka_get_plan':
      result = await handleGetPlan(args);
      break;
    default:
      result = {
        success: false,
        error: `Unknown tool: ${name}`,
      };
  }

  // Track this MCP tool call as an activity (linked to Session Work feature)
  if (TRACK_ACTIVITIES) {
    try {
      const projectPath = getProjectPath(args.project_path as string | undefined);
      await db.recordMcpActivity(projectPath, name, args, result);
    } catch (error) {
      // Don't fail the tool call if activity tracking fails
      console.error('[ijoka-mcp] Failed to record activity:', error);
    }
  }

  return result;
}

// =============================================================================
// TOOL HANDLERS
// =============================================================================

async function handleStatus(args: Record<string, unknown>): Promise<ToolResult> {
  const projectPath = getProjectPath(args.project_path as string | undefined);
  const includeInsights = args.include_insights === true;
  const includeBlockers = args.include_blockers === true;

  // Ensure project exists
  let project = await db.getProjectByPath(projectPath);
  if (!project) {
    project = await db.upsertProject({ path: projectPath });
  }

  // Get current feature and stats
  const [currentFeature, stats, activeSession] = await Promise.all([
    db.getActiveFeature(projectPath),
    db.getProjectStats(projectPath),
    db.getActiveSession(projectPath),
  ]);

  const result: ToolResult = {
    success: true,
    project: {
      id: project.id,
      name: project.name,
      path: project.path,
    },
    current_feature: currentFeature,
    stats,
    active_session: activeSession,
  };

  // Optionally include insights
  if (includeInsights) {
    const insights = await db.getInsights(undefined, undefined, 5);
    result.recent_insights = insights;
  }

  // Optionally include blockers
  if (includeBlockers) {
    const blockers = await db.getBlockedFeatures(projectPath);
    result.active_blockers = blockers;
  }

  return result;
}

async function handleStartFeature(args: Record<string, unknown>): Promise<ToolResult> {
  const projectPath = getProjectPath();
  const featureId = args.feature_id as string | undefined;
  const agent = (args.agent as string) || 'claude-code';

  let feature: db.Feature | null;

  if (featureId) {
    // Start specific feature
    feature = await db.startFeature(featureId, agent);
  } else {
    // Get next available feature
    feature = await db.getNextFeature(projectPath);
    if (!feature) {
      return {
        success: false,
        error: 'No pending features available to start',
      };
    }
    if (!feature.id) {
      return {
        success: false,
        error: 'Next feature found but has no ID - database may be corrupted',
      };
    }
    feature = await db.startFeature(feature.id, agent);
  }

  if (!feature) {
    return {
      success: false,
      error: 'Failed to start feature',
    };
  }

  return {
    success: true,
    feature,
    message: `Started feature: ${feature.description}`,
  };
}

async function handleCompleteFeature(args: Record<string, unknown>): Promise<ToolResult> {
  const projectPath = getProjectPath();
  let featureId = args.feature_id as string | undefined;

  // If no feature_id, use currently active feature
  if (!featureId) {
    const activeFeature = await db.getActiveFeature(projectPath);
    if (!activeFeature) {
      return {
        success: false,
        error: 'No active feature to complete',
      };
    }
    featureId = activeFeature.id;
  }

  const feature = await db.completeFeature(featureId);
  if (!feature) {
    return {
      success: false,
      error: `Feature not found: ${featureId}`,
    };
  }

  const stats = await db.getProjectStats(projectPath);

  return {
    success: true,
    feature,
    stats,
    message: `Completed feature: ${feature.description}`,
  };
}

async function handleBlockFeature(args: Record<string, unknown>): Promise<ToolResult> {
  const projectPath = getProjectPath();
  let featureId = args.feature_id as string | undefined;
  const reason = args.reason as string;
  const blockingFeatureId = args.blocking_feature_id as string | undefined;

  if (!reason) {
    return {
      success: false,
      error: 'Reason is required to block a feature',
    };
  }

  // If no feature_id, use currently active feature
  if (!featureId) {
    const activeFeature = await db.getActiveFeature(projectPath);
    if (!activeFeature) {
      return {
        success: false,
        error: 'No active feature to block',
      };
    }
    featureId = activeFeature.id;
  }

  const feature = await db.blockFeature(featureId, reason, blockingFeatureId);
  if (!feature) {
    return {
      success: false,
      error: `Feature not found: ${featureId}`,
    };
  }

  return {
    success: true,
    feature,
    message: `Blocked feature: ${feature.description}. Reason: ${reason}`,
  };
}

async function handleRecordInsight(args: Record<string, unknown>): Promise<ToolResult> {
  const description = args.description as string;
  const patternType = args.pattern_type as db.Insight['pattern_type'];
  const tags = args.tags as string[] | undefined;
  const featureId = args.feature_id as string | undefined;

  if (!description || !patternType) {
    return {
      success: false,
      message: 'Description and pattern_type are required',
    };
  }

  const insight = await db.recordInsight(
    { description, pattern_type: patternType, tags },
    featureId
  );

  return {
    success: true,
    insight,
    message: `Recorded insight: ${description.substring(0, 50)}...`,
  };
}

async function handleGetInsights(args: Record<string, unknown>): Promise<ToolResult> {
  const query = args.query as string | undefined;
  const tags = args.tags as string[] | undefined;
  const limit = (args.limit as number) || 5;

  const insights = await db.getInsights(query, tags, limit);

  return {
    success: true,
    insights,
    count: insights.length,
  };
}

async function handleCreateFeature(args: Record<string, unknown>): Promise<ToolResult> {
  const projectPath = getProjectPath();
  const description = args.description as string;
  const category = args.category as string;
  const steps = args.steps as string[] | undefined;
  const priority = args.priority as number | undefined;

  if (!description || !category) {
    return {
      success: false,
      message: 'Description and category are required',
    };
  }

  // Ensure project exists
  await db.upsertProject({ path: projectPath });

  const feature = await db.createFeature(projectPath, {
    description,
    category,
    steps,
    priority,
  });

  return {
    success: true,
    feature,
    message: `Created feature: ${description}`,
  };
}

async function handleSetPlan(args: Record<string, unknown>): Promise<ToolResult> {
  const projectPath = getProjectPath(args.project_path as string | undefined);
  const steps = args.steps as string[];
  let featureId = args.feature_id as string | undefined;

  if (!steps || steps.length === 0) {
    return {
      success: false,
      error: 'Steps array is required',
    };
  }

  // Get feature
  if (!featureId) {
    const activeFeature = await db.getActiveFeature(projectPath);
    if (!activeFeature) {
      return {
        success: false,
        error: 'No active feature. Start a feature first.',
      };
    }
    featureId = activeFeature.id;
  }

  // Sync steps
  const createdSteps = await db.syncStepsFromArray(featureId, steps);

  return {
    success: true,
    feature_id: featureId,
    steps: createdSteps,
    message: `Created/updated ${createdSteps.length} steps`,
  };
}

async function handleCheckpoint(args: Record<string, unknown>): Promise<ToolResult> {
  const projectPath = getProjectPath(args.project_path as string | undefined);
  const stepCompleted = args.step_completed as string | undefined;
  const currentActivity = args.current_activity as string | undefined;

  const activeFeature = await db.getActiveFeature(projectPath);
  if (!activeFeature) {
    return {
      success: true,
      message: 'No active feature',
      warnings: [],
    };
  }

  const activeStep = await db.getActiveStep(activeFeature.id);
  const warnings: string[] = [];

  // Mark step completed if specified
  if (stepCompleted && activeStep) {
    if (
      activeStep.description.toLowerCase().includes(stepCompleted.toLowerCase()) ||
      stepCompleted.toLowerCase().includes(activeStep.description.toLowerCase())
    ) {
      await db.updateStepStatus(activeStep.id, 'completed');

      // Start next step
      const steps = await db.getSteps(activeFeature.id);
      const nextStep = steps.find((s) => s.status === 'pending');
      if (nextStep) {
        await db.updateStepStatus(nextStep.id, 'in_progress');
      }
    }
  }

  // Get updated state
  const steps = await db.getSteps(activeFeature.id);
  const completed = steps.filter((s) => s.status === 'completed').length;
  const total = steps.length;

  // Simple drift check based on current_activity vs active step
  const newActiveStep = await db.getActiveStep(activeFeature.id);
  if (newActiveStep && currentActivity) {
    const stepKeywords = new Set(newActiveStep.description.toLowerCase().split(/\s+/));
    const activityKeywords = new Set(currentActivity.toLowerCase().split(/\s+/));
    const overlap = [...stepKeywords].filter((k) => activityKeywords.has(k)).length;

    if (overlap < 2 && stepKeywords.size > 3) {
      warnings.push(
        `Current activity may not align with step: "${newActiveStep.description}"`
      );
    }
  }

  return {
    success: true,
    feature: {
      id: activeFeature.id,
      description: activeFeature.description,
    },
    active_step: newActiveStep,
    progress: {
      completed,
      total,
      percentage: Math.round((completed / total) * 100),
    },
    warnings,
  };
}

async function handleGetPlan(args: Record<string, unknown>): Promise<ToolResult> {
  const projectPath = getProjectPath(args.project_path as string | undefined);
  let featureId = args.feature_id as string | undefined;

  if (!featureId) {
    const activeFeature = await db.getActiveFeature(projectPath);
    if (!activeFeature) {
      return {
        success: true,
        message: 'No active feature',
        steps: [],
      };
    }
    featureId = activeFeature.id;
  }

  const feature = await db.getFeatureById(featureId);
  const steps = await db.getSteps(featureId);
  const activeStep = await db.getActiveStep(featureId);

  const completed = steps.filter((s) => s.status === 'completed').length;

  return {
    success: true,
    feature: feature
      ? {
          id: feature.id,
          description: feature.description,
          status: feature.status,
        }
      : null,
    steps: steps.map((s) => ({
      order: s.step_order,
      description: s.description,
      status: s.status,
    })),
    active_step: activeStep
      ? {
          order: activeStep.step_order,
          description: activeStep.description,
        }
      : null,
    progress: {
      completed,
      total: steps.length,
      percentage: steps.length > 0 ? Math.round((completed / steps.length) * 100) : 0,
    },
  };
}
