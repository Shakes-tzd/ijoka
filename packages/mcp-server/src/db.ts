/**
 * Graph Database Client for MCP Server
 *
 * Provides connection to Memgraph/Neo4j for the MCP server.
 */

import neo4j, { Driver, Session as Neo4jSession, auth } from 'neo4j-driver';
import { randomUUID } from 'crypto';

export interface GraphDbConfig {
  uri: string;
  user?: string;
  password?: string;
  database?: string;
}

let driver: Driver | null = null;
let config: GraphDbConfig | null = null;

/**
 * Initialize connection to graph database
 */
export async function initGraphDB(dbConfig: GraphDbConfig): Promise<void> {
  config = dbConfig;

  driver = neo4j.driver(
    dbConfig.uri,
    dbConfig.user && dbConfig.password
      ? auth.basic(dbConfig.user, dbConfig.password)
      : auth.basic('', ''),
    {
      maxConnectionPoolSize: 10,
      connectionAcquisitionTimeout: 30000,
    }
  );

  // Verify connectivity
  await driver.verifyConnectivity();
  console.error('[ijoka-mcp] Connected to graph database');
}

/**
 * Close graph database connection
 */
export async function closeGraphDB(): Promise<void> {
  if (driver) {
    await driver.close();
    driver = null;
  }
}

/**
 * Check if connected to graph database
 */
export function isConnected(): boolean {
  return driver !== null;
}

/**
 * Get a session for running queries
 */
function getSession(mode: 'READ' | 'WRITE' = 'READ'): Neo4jSession {
  if (!driver) {
    throw new Error('Graph database not initialized');
  }
  return driver.session({
    database: config?.database || 'memgraph',
    defaultAccessMode: mode === 'READ' ? neo4j.session.READ : neo4j.session.WRITE,
  });
}

/**
 * Run a read query
 */
export async function runQuery<T>(
  cypher: string,
  params?: Record<string, unknown>
): Promise<T[]> {
  const session = getSession('READ');
  try {
    const result = await session.run(cypher, params);
    return result.records.map((record) => record.toObject() as T);
  } finally {
    await session.close();
  }
}

/**
 * Run a write query
 */
export async function runWriteQuery<T>(
  cypher: string,
  params?: Record<string, unknown>
): Promise<T[]> {
  const session = getSession('WRITE');
  try {
    const result = await session.run(cypher, params);
    return result.records.map((record) => record.toObject() as T);
  } finally {
    await session.close();
  }
}

// =============================================================================
// TYPE DEFINITIONS
// =============================================================================

export interface Project {
  id: string;
  path: string;
  name: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export interface Feature {
  id: string;
  description: string;
  category: string;
  status: 'pending' | 'in_progress' | 'blocked' | 'complete';
  priority: number;
  steps?: string[];
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
  work_count: number;
  assigned_agent?: string;
  block_reason?: string;
}

export interface AgentSession {
  id: string;
  agent: string;
  status: 'active' | 'ended' | 'stale';
  started_at?: string;
  ended_at?: string;
  last_activity?: string;
  event_count: number;
  is_subagent: boolean;
}

export interface Insight {
  id: string;
  description: string;
  pattern_type: 'solution' | 'anti_pattern' | 'best_practice' | 'tool_usage';
  tags?: string[];
  created_at?: string;
  usage_count: number;
  effectiveness_score?: number;
}

export interface Step {
  id: string;
  feature_id: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'skipped';
  step_order: number;
  expected_tools?: string[];
  created_at?: string;
  started_at?: string;
  completed_at?: string;
}

export interface ProjectStats {
  total: number;
  pending: number;
  in_progress: number;
  blocked: number;
  complete: number;
  completion_percentage: number;
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

function nodeToProject(node: Record<string, unknown>): Project {
  const rawNode = node.p as Record<string, unknown>;
  // Handle both direct properties and properties object from neo4j-driver
  const p = (rawNode?.properties as Record<string, unknown>) || rawNode || {};
  return {
    id: p.id as string,
    path: p.path as string,
    name: p.name as string,
    description: p.description as string | undefined,
    created_at: p.created_at?.toString(),
    updated_at: p.updated_at?.toString(),
  };
}

function nodeToFeature(node: Record<string, unknown>): Feature {
  // Neo4j driver returns nodes as objects with properties nested
  const rawNode = node.f as Record<string, unknown>;
  // Handle both direct properties and properties object from neo4j-driver
  const f = (rawNode?.properties as Record<string, unknown>) || rawNode || {};
  return {
    id: f.id as string,
    description: f.description as string,
    category: f.category as string,
    status: f.status as Feature['status'],
    priority: Number(f.priority) || 0,
    steps: f.steps as string[] | undefined,
    created_at: f.created_at?.toString(),
    updated_at: f.updated_at?.toString(),
    completed_at: f.completed_at?.toString(),
    work_count: Number(f.work_count) || 0,
    assigned_agent: f.assigned_agent as string | undefined,
    block_reason: f.block_reason as string | undefined,
  };
}

function nodeToInsight(node: Record<string, unknown>): Insight {
  const rawNode = node.i as Record<string, unknown>;
  // Handle both direct properties and properties object from neo4j-driver
  const i = (rawNode?.properties as Record<string, unknown>) || rawNode || {};
  return {
    id: i.id as string,
    description: i.description as string,
    pattern_type: i.pattern_type as Insight['pattern_type'],
    tags: i.tags as string[] | undefined,
    created_at: i.created_at?.toString(),
    usage_count: Number(i.usage_count) || 0,
    effectiveness_score: i.effectiveness_score as number | undefined,
  };
}

function nodeToStep(node: Record<string, unknown>): Step {
  const rawNode = node.s as Record<string, unknown>;
  // Handle both direct properties and properties object from neo4j-driver
  const s = (rawNode?.properties as Record<string, unknown>) || rawNode || {};
  return {
    id: s.id as string,
    feature_id: s.feature_id as string,
    description: s.description as string,
    status: s.status as Step['status'],
    step_order: Number(s.step_order) || 0,
    expected_tools: s.expected_tools as string[] | undefined,
    created_at: s.created_at?.toString(),
    started_at: s.started_at?.toString(),
    completed_at: s.completed_at?.toString(),
  };
}

// =============================================================================
// PROJECT OPERATIONS
// =============================================================================

export async function getProjectByPath(path: string): Promise<Project | null> {
  const results = await runQuery<Record<string, unknown>>(
    'MATCH (p:Project {path: $path}) RETURN p',
    { path }
  );
  return results.length > 0 ? nodeToProject(results[0]) : null;
}

export async function upsertProject(project: Partial<Project> & { path: string }): Promise<Project> {
  const id = randomUUID();
  const results = await runWriteQuery<Record<string, unknown>>(
    `
    MERGE (p:Project {path: $path})
    ON CREATE SET
      p.id = $id,
      p.name = $name,
      p.description = $description,
      p.created_at = datetime(),
      p.updated_at = datetime()
    ON MATCH SET
      p.name = COALESCE($name, p.name),
      p.description = COALESCE($description, p.description),
      p.updated_at = datetime()
    RETURN p
    `,
    {
      id,
      path: project.path,
      name: project.name || project.path.split('/').pop() || 'Unknown',
      description: project.description || null,
    }
  );
  return nodeToProject(results[0]);
}

// =============================================================================
// FEATURE OPERATIONS
// =============================================================================

export async function getFeaturesForProject(projectPath: string): Promise<Feature[]> {
  const results = await runQuery<Record<string, unknown>>(
    `
    MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $projectPath})
    RETURN f
    ORDER BY f.priority DESC, f.created_at ASC
    `,
    { projectPath }
  );
  return results.map(nodeToFeature);
}

export async function getActiveFeature(projectPath: string): Promise<Feature | null> {
  const results = await runQuery<Record<string, unknown>>(
    `
    MATCH (f:Feature {status: 'in_progress'})-[:BELONGS_TO]->(p:Project {path: $projectPath})
    RETURN f
    LIMIT 1
    `,
    { projectPath }
  );
  return results.length > 0 ? nodeToFeature(results[0]) : null;
}

export async function getNextFeature(projectPath: string): Promise<Feature | null> {
  const results = await runQuery<Record<string, unknown>>(
    `
    MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $projectPath})
    WHERE f.status = 'pending'
    AND NOT EXISTS {
      MATCH (f)-[:DEPENDS_ON {dependency_type: 'blocks'}]->(dep:Feature)
      WHERE dep.status <> 'complete'
    }
    RETURN f
    ORDER BY f.priority DESC, f.created_at ASC
    LIMIT 1
    `,
    { projectPath }
  );
  return results.length > 0 ? nodeToFeature(results[0]) : null;
}

export async function startFeature(featureId: string, agent?: string): Promise<Feature | null> {
  if (!featureId) {
    throw new Error('featureId is required');
  }

  // Get current status for StatusEvent
  const currentFeature = await runQuery<Record<string, unknown>>(
    'MATCH (f:Feature {id: $featureId}) RETURN f.status as status',
    { featureId }
  );
  const fromStatus = currentFeature[0]?.status as string || 'pending';

  // Create StatusEvent for audit trail
  await createStatusEvent(featureId, fromStatus, 'in_progress', 'mcp:ijoka_start_feature', agent);

  const results = await runWriteQuery<Record<string, unknown>>(
    `
    MATCH (f:Feature {id: $featureId})
    SET f.status = 'in_progress',
        f.assigned_agent = $agent,
        f.updated_at = datetime()
    RETURN f
    `,
    { featureId, agent: agent || null }
  );
  if (results.length === 0) {
    return null;
  }
  return nodeToFeature(results[0]);
}

/**
 * Create a StatusEvent for temporal audit trail
 */
export async function createStatusEvent(
  featureId: string,
  fromStatus: string,
  toStatus: string,
  triggeredBy: string,
  agent?: string
): Promise<void> {
  const eventId = randomUUID();
  await runWriteQuery(
    `
    MATCH (f:Feature {id: $featureId})
    CREATE (se:StatusEvent {
      id: $eventId,
      from_status: $fromStatus,
      to_status: $toStatus,
      at: datetime(),
      by: $triggeredBy,
      agent: $agent
    })-[:CHANGED_STATUS]->(f)
    `,
    {
      featureId,
      eventId,
      fromStatus,
      toStatus,
      triggeredBy,
      agent: agent || null,
    }
  );
}

export async function completeFeature(featureId: string): Promise<Feature | null> {
  if (!featureId) {
    throw new Error('featureId is required');
  }

  // Get current status for StatusEvent
  const currentFeature = await runQuery<Record<string, unknown>>(
    'MATCH (f:Feature {id: $featureId}) RETURN f.status as status',
    { featureId }
  );
  const fromStatus = currentFeature[0]?.status as string || 'in_progress';

  // Create StatusEvent for audit trail
  await createStatusEvent(featureId, fromStatus, 'complete', 'mcp:ijoka_complete_feature');

  const results = await runWriteQuery<Record<string, unknown>>(
    `
    MATCH (f:Feature {id: $featureId})
    SET f.status = 'complete',
        f.completed_at = datetime(),
        f.updated_at = datetime()
    RETURN f
    `,
    { featureId }
  );
  if (results.length === 0) {
    return null;
  }
  return nodeToFeature(results[0]);
}

export async function blockFeature(featureId: string, reason: string, blockingFeatureId?: string): Promise<Feature | null> {
  if (!featureId) {
    throw new Error('featureId is required');
  }

  // Get current status for StatusEvent
  const currentFeature = await runQuery<Record<string, unknown>>(
    'MATCH (f:Feature {id: $featureId}) RETURN f.status as status',
    { featureId }
  );
  const fromStatus = currentFeature[0]?.status as string || 'in_progress';

  // Create StatusEvent for audit trail
  await createStatusEvent(featureId, fromStatus, 'blocked', 'mcp:ijoka_block_feature');

  // First, update the feature status
  const results = await runWriteQuery<Record<string, unknown>>(
    `
    MATCH (f:Feature {id: $featureId})
    SET f.status = 'blocked',
        f.block_reason = $reason,
        f.updated_at = datetime()
    RETURN f
    `,
    { featureId, reason }
  );

  if (results.length === 0) {
    return null;
  }

  // If there's a blocking feature, create a dependency relationship
  if (blockingFeatureId) {
    await runWriteQuery(
      `
      MATCH (f:Feature {id: $featureId})
      MATCH (blocker:Feature {id: $blockingFeatureId})
      MERGE (f)-[:DEPENDS_ON {dependency_type: 'blocks'}]->(blocker)
      `,
      { featureId, blockingFeatureId }
    );
  }

  return nodeToFeature(results[0]);
}

export async function createFeature(
  projectPath: string,
  feature: {
    description: string;
    category: string;
    steps?: string[];
    priority?: number;
  }
): Promise<Feature> {
  const id = randomUUID();
  const results = await runWriteQuery<Record<string, unknown>>(
    `
    MATCH (p:Project {path: $projectPath})
    CREATE (f:Feature {
      id: $id,
      description: $description,
      category: $category,
      status: 'pending',
      priority: $priority,
      steps: $steps,
      created_at: datetime(),
      updated_at: datetime(),
      work_count: 0
    })-[:BELONGS_TO]->(p)
    RETURN f
    `,
    {
      id,
      projectPath,
      description: feature.description,
      category: feature.category,
      steps: feature.steps || [],
      priority: feature.priority || 0,
    }
  );
  return nodeToFeature(results[0]);
}

export async function getProjectStats(projectPath: string): Promise<ProjectStats> {
  const results = await runQuery<Record<string, unknown>>(
    `
    MATCH (p:Project {path: $projectPath})
    OPTIONAL MATCH (f:Feature)-[:BELONGS_TO]->(p)
    WITH p,
         count(f) as total,
         sum(CASE WHEN f.status = 'pending' THEN 1 ELSE 0 END) as pending,
         sum(CASE WHEN f.status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
         sum(CASE WHEN f.status = 'blocked' THEN 1 ELSE 0 END) as blocked,
         sum(CASE WHEN f.status = 'complete' THEN 1 ELSE 0 END) as complete
    RETURN total, pending, in_progress, blocked, complete
    `,
    { projectPath }
  );

  if (results.length === 0) {
    return {
      total: 0,
      pending: 0,
      in_progress: 0,
      blocked: 0,
      complete: 0,
      completion_percentage: 0,
    };
  }

  const r = results[0];
  const total = Number(r.total) || 0;
  const complete = Number(r.complete) || 0;

  return {
    total,
    pending: Number(r.pending) || 0,
    in_progress: Number(r.in_progress) || 0,
    blocked: Number(r.blocked) || 0,
    complete,
    completion_percentage: total > 0 ? Math.round((complete / total) * 100) : 0,
  };
}

export async function getBlockedFeatures(projectPath: string): Promise<Feature[]> {
  const results = await runQuery<Record<string, unknown>>(
    `
    MATCH (f:Feature {status: 'blocked'})-[:BELONGS_TO]->(p:Project {path: $projectPath})
    RETURN f
    ORDER BY f.priority DESC
    `,
    { projectPath }
  );
  return results.map(nodeToFeature);
}

export async function getFeatureById(featureId: string): Promise<Feature | null> {
  const results = await runQuery<Record<string, unknown>>(
    'MATCH (f:Feature {id: $featureId}) RETURN f',
    { featureId }
  );
  return results.length > 0 ? nodeToFeature(results[0]) : null;
}

// =============================================================================
// STEP OPERATIONS
// =============================================================================

export async function createStep(
  featureId: string,
  description: string,
  order: number,
  status: string = 'pending'
): Promise<Step> {
  const id = randomUUID();
  const results = await runWriteQuery<Record<string, unknown>>(
    `
    MATCH (f:Feature {id: $featureId})
    CREATE (s:Step {
      id: $id,
      feature_id: $featureId,
      description: $description,
      status: $status,
      step_order: $order,
      created_at: datetime()
    })-[:BELONGS_TO]->(f)
    RETURN s
    `,
    { featureId, id, description, status, order }
  );

  return nodeToStep(results[0]);
}

export async function getSteps(featureId: string): Promise<Step[]> {
  const results = await runQuery<Record<string, unknown>>(
    `
    MATCH (s:Step)-[:BELONGS_TO]->(f:Feature {id: $featureId})
    RETURN s
    ORDER BY s.step_order ASC
    `,
    { featureId }
  );

  return results.map(nodeToStep);
}

export async function getActiveStep(featureId: string): Promise<Step | null> {
  // First try in_progress
  let results = await runQuery<Record<string, unknown>>(
    `
    MATCH (s:Step)-[:BELONGS_TO]->(f:Feature {id: $featureId})
    WHERE s.status = 'in_progress'
    RETURN s
    ORDER BY s.step_order ASC
    LIMIT 1
    `,
    { featureId }
  );

  if (results.length > 0) {
    return nodeToStep(results[0]);
  }

  // Fall back to first pending
  results = await runQuery<Record<string, unknown>>(
    `
    MATCH (s:Step)-[:BELONGS_TO]->(f:Feature {id: $featureId})
    WHERE s.status = 'pending'
    RETURN s
    ORDER BY s.step_order ASC
    LIMIT 1
    `,
    { featureId }
  );

  return results.length > 0 ? nodeToStep(results[0]) : null;
}

export async function updateStepStatus(stepId: string, status: string): Promise<Step | null> {
  const timeField =
    status === 'in_progress' ? 'started_at' : status === 'completed' ? 'completed_at' : null;

  const setClauses = ['s.status = $status'];
  if (timeField) {
    setClauses.push(`s.${timeField} = datetime()`);
  }

  const results = await runWriteQuery<Record<string, unknown>>(
    `
    MATCH (s:Step {id: $stepId})
    SET ${setClauses.join(', ')}
    RETURN s
    `,
    { stepId, status }
  );

  return results.length > 0 ? nodeToStep(results[0]) : null;
}

export async function syncStepsFromArray(featureId: string, stepDescriptions: string[]): Promise<Step[]> {
  const existingSteps = await getSteps(featureId);
  const existingByDesc = new Map(existingSteps.map((s) => [s.description, s]));

  const steps: Step[] = [];

  for (let i = 0; i < stepDescriptions.length; i++) {
    const desc = stepDescriptions[i];
    const existing = existingByDesc.get(desc);

    if (existing) {
      steps.push(existing);
    } else {
      const step = await createStep(featureId, desc, i);
      steps.push(step);
    }
  }

  // Mark steps not in new list as skipped
  const newDescs = new Set(stepDescriptions);
  for (const step of existingSteps) {
    if (!newDescs.has(step.description)) {
      await updateStepStatus(step.id, 'skipped');
    }
  }

  return steps;
}

// =============================================================================
// INSIGHT OPERATIONS
// =============================================================================

export async function recordInsight(
  insight: {
    description: string;
    pattern_type: Insight['pattern_type'];
    tags?: string[];
  },
  featureId?: string
): Promise<Insight> {
  const id = randomUUID();
  const results = await runWriteQuery<Record<string, unknown>>(
    `
    CREATE (i:Insight {
      id: $id,
      description: $description,
      pattern_type: $pattern_type,
      tags: $tags,
      created_at: datetime(),
      usage_count: 0
    })
    RETURN i
    `,
    {
      id,
      description: insight.description,
      pattern_type: insight.pattern_type,
      tags: insight.tags || [],
    }
  );

  const createdInsight = nodeToInsight(results[0]);

  // Link to feature if provided
  if (featureId) {
    await runWriteQuery(
      `
      MATCH (i:Insight {id: $insightId})
      MATCH (f:Feature {id: $featureId})
      MERGE (i)-[:LEARNED_FROM]->(f)
      `,
      { insightId: createdInsight.id, featureId }
    );
  }

  return createdInsight;
}

export async function getInsights(
  query?: string,
  tags?: string[],
  limit: number = 5
): Promise<Insight[]> {
  // Ensure limit is an integer for Memgraph
  const limitInt = neo4j.int(Math.floor(limit));
  let cypher: string;
  const params: Record<string, unknown> = { limit: limitInt };

  if (query) {
    cypher = `
      MATCH (i:Insight)
      WHERE i.description CONTAINS $query
      RETURN i
      ORDER BY i.usage_count DESC, i.created_at DESC
      LIMIT $limit
    `;
    params.query = query;
  } else if (tags && tags.length > 0) {
    cypher = `
      MATCH (i:Insight)
      WHERE any(tag IN $tags WHERE tag IN i.tags)
      RETURN i
      ORDER BY i.usage_count DESC, i.created_at DESC
      LIMIT $limit
    `;
    params.tags = tags;
  } else {
    cypher = `
      MATCH (i:Insight)
      RETURN i
      ORDER BY i.usage_count DESC, i.created_at DESC
      LIMIT $limit
    `;
  }

  const results = await runQuery<Record<string, unknown>>(cypher, params);
  return results.map(nodeToInsight);
}

// =============================================================================
// SESSION WORK FEATURE (for meta activities)
// =============================================================================

const SESSION_WORK_DESCRIPTION = 'Session Work - Project management and meta activities';

/**
 * Get or create the Session Work pseudo-feature for a project.
 * This feature captures meta activities like MCP tool calls.
 */
export async function getOrCreateSessionWorkFeature(projectPath: string): Promise<Feature> {
  // Check if Session Work feature already exists
  const existingResults = await runQuery<Record<string, unknown>>(
    `
    MATCH (f:Feature)-[:BELONGS_TO]->(p:Project {path: $projectPath})
    WHERE f.is_session_work = true
    RETURN f
    LIMIT 1
    `,
    { projectPath }
  );

  if (existingResults.length > 0) {
    return nodeToFeature(existingResults[0]);
  }

  // Ensure project exists
  await upsertProject({ path: projectPath });

  // Create the Session Work feature
  const id = randomUUID();
  const results = await runWriteQuery<Record<string, unknown>>(
    `
    MATCH (p:Project {path: $projectPath})
    CREATE (f:Feature {
      id: $id,
      description: $description,
      category: 'infrastructure',
      status: 'pending',
      priority: -1,
      steps: ['Collects meta activities automatically'],
      created_at: datetime(),
      updated_at: datetime(),
      work_count: 0,
      is_session_work: true
    })-[:BELONGS_TO]->(p)
    RETURN f
    `,
    {
      id,
      projectPath,
      description: SESSION_WORK_DESCRIPTION,
    }
  );

  return nodeToFeature(results[0]);
}

// =============================================================================
// ACTIVITY/EVENT TRACKING
// =============================================================================

export interface ActivityEvent {
  id: string;
  event_type: string;
  tool_name: string;
  payload: Record<string, unknown>;
  created_at?: string;
  session_id?: string;
}

/**
 * Record an MCP tool activity, linking it to the Session Work feature.
 *
 * @param projectPath - Project directory path
 * @param toolName - Name of the MCP tool called
 * @param args - Tool arguments (may include source_agent and session_id)
 * @param result - Tool result with success status
 */
export async function recordMcpActivity(
  projectPath: string,
  toolName: string,
  args: Record<string, unknown>,
  result: { success: boolean; [key: string]: unknown }
): Promise<void> {
  // Get the Session Work feature
  const sessionWorkFeature = await getOrCreateSessionWorkFeature(projectPath);

  // Extract agent identification from args, env vars, or defaults
  const sourceAgent = (args.source_agent as string)
    || process.env.IJOKA_AGENT_ID
    || 'unknown';
  const sessionId = (args.session_id as string)
    || process.env.IJOKA_SESSION_ID
    || process.env.CLAUDE_SESSION_ID
    || `mcp-${Date.now()}`;

  const eventId = randomUUID();
  const summary = `MCP: ${toolName}`;
  const payload = {
    tool: toolName,
    args: JSON.stringify(args).substring(0, 500),
    success: result.success,
    resultSummary: JSON.stringify(result).substring(0, 200),
    isMetaTool: true,
  };

  // Create the event and link it to the Session Work feature
  // Use `timestamp` field name to match Rust/Python conventions
  await runWriteQuery(
    `
    MATCH (f:Feature {id: $featureId})
    CREATE (e:Event {
      id: $eventId,
      event_type: 'McpToolCall',
      tool_name: $toolName,
      payload: $payload,
      timestamp: datetime(),
      source_agent: $sourceAgent,
      session_id: $sessionId,
      success: $success,
      summary: $summary
    })-[:LINKED_TO]->(f)
    `,
    {
      eventId,
      featureId: sessionWorkFeature.id,
      toolName,
      payload: JSON.stringify(payload),
      sourceAgent,
      sessionId,
      success: result.success,
      summary,
    }
  );

  // Increment work count on Session Work feature
  await runWriteQuery(
    `
    MATCH (f:Feature {id: $featureId})
    SET f.work_count = f.work_count + 1,
        f.updated_at = datetime()
    `,
    { featureId: sessionWorkFeature.id }
  );

  console.error(`[ijoka-mcp] Recorded activity: ${toolName} (agent: ${sourceAgent}) -> Session Work feature`);
}

// =============================================================================
// SESSION OPERATIONS
// =============================================================================

export async function getActiveSession(projectPath: string): Promise<AgentSession | null> {
  const results = await runQuery<Record<string, unknown>>(
    `
    MATCH (s:Session {status: 'active'})-[:IN_PROJECT]->(p:Project {path: $projectPath})
    RETURN s
    ORDER BY s.last_activity DESC
    LIMIT 1
    `,
    { projectPath }
  );

  if (results.length === 0) return null;

  const rawNode = results[0].s as Record<string, unknown>;
  // Handle both direct properties and properties object from neo4j-driver
  const s = (rawNode?.properties as Record<string, unknown>) || rawNode || {};
  return {
    id: s.id as string,
    agent: s.agent as string,
    status: s.status as AgentSession['status'],
    started_at: s.started_at?.toString(),
    ended_at: s.ended_at?.toString(),
    last_activity: s.last_activity?.toString(),
    event_count: Number(s.event_count) || 0,
    is_subagent: Boolean(s.is_subagent),
  };
}
