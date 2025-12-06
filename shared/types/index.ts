/**
 * AgentKanban Shared Types
 * 
 * These types are shared between the desktop app and Claude plugin
 */

// =============================================================================
// Feature List (Anthropic's long-running agent pattern)
// =============================================================================

export interface Feature {
  /** Feature category (functional, ui, security, performance, etc.) */
  category: FeatureCategory;
  
  /** Human-readable description of what the feature does */
  description: string;
  
  /** Steps to verify the feature works (test script for agent) */
  steps: string[];
  
  /** Whether the feature passes all verification steps */
  passes: boolean;
  
  /** Optional: Feature is currently being worked on */
  inProgress?: boolean;
  
  /** Optional: Which agent is working on this */
  agent?: string;
  
  /** Optional: Unique identifier (generated if not provided) */
  id?: string;
}

export type FeatureCategory = 
  | 'functional'
  | 'ui'
  | 'security'
  | 'performance'
  | 'documentation'
  | 'testing'
  | 'infrastructure'
  | 'refactoring';

export interface FeatureList {
  features: Feature[];
  metadata?: {
    projectName?: string;
    createdAt?: string;
    updatedAt?: string;
  };
}

// =============================================================================
// Agent Events
// =============================================================================

export interface AgentEvent {
  /** Unique event ID */
  id?: number;
  
  /** Event type */
  eventType: AgentEventType;
  
  /** Which agent generated this event */
  sourceAgent: AgentSource;
  
  /** Session identifier */
  sessionId: string;
  
  /** Project directory path */
  projectDir: string;
  
  /** Tool name (for tool events) */
  toolName?: string;
  
  /** Additional payload data */
  payload?: Record<string, unknown>;
  
  /** ISO timestamp */
  createdAt: string;
}

export type AgentEventType =
  | 'SessionStart'
  | 'SessionEnd'
  | 'ToolUse'
  | 'FeatureStarted'
  | 'FeatureCompleted'
  | 'Error'
  | 'Progress';

export type AgentSource =
  | 'claude-code'
  | 'codex-cli'
  | 'gemini-cli'
  | 'hook'
  | 'file-watch'
  | 'unknown';

// =============================================================================
// Sessions
// =============================================================================

export interface AgentSession {
  /** Unique session identifier */
  sessionId: string;
  
  /** Which agent is running */
  sourceAgent: AgentSource;
  
  /** Project directory */
  projectDir: string;
  
  /** Session start time (ISO) */
  startedAt: string;
  
  /** Last activity time (ISO) */
  lastActivity: string;
  
  /** Session status */
  status: SessionStatus;
  
  /** Current feature being worked on */
  currentFeature?: string;
}

export type SessionStatus = 'active' | 'idle' | 'ended';

// =============================================================================
// Statistics
// =============================================================================

export interface ProjectStats {
  /** Total number of features */
  total: number;
  
  /** Completed features */
  completed: number;
  
  /** In-progress features */
  inProgress: number;
  
  /** Completion percentage */
  percentage: number;
  
  /** Active sessions count */
  activeSessions: number;
  
  /** Features by category */
  byCategory: Record<FeatureCategory, { total: number; completed: number }>;
}

// =============================================================================
// HTTP API Types
// =============================================================================

export interface HookEventPayload {
  eventType: AgentEventType;
  sourceAgent: AgentSource;
  sessionId: string;
  projectDir: string;
  toolName?: string;
  payload?: Record<string, unknown>;
}

export interface FeatureUpdatePayload {
  projectDir: string;
  stats: {
    total: number;
    completed: number;
    percentage: number;
  };
  changedFeatures: Array<{
    description: string;
    category: FeatureCategory;
    passes: boolean;
  }>;
}

export interface ApiResponse<T = unknown> {
  ok: boolean;
  data?: T;
  error?: string;
}

// =============================================================================
// Claude Plugin Types
// =============================================================================

export interface PluginConfig {
  watchedProjects: string[];
  syncServerPort: number;
  notificationsEnabled: boolean;
  autoStartSession: boolean;
}

export interface HookInput {
  hook_type: string;
  session_id: string;
  project_dir: string;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  tool_output?: string;
  transcript_path?: string;
}

export interface HookOutput {
  continue: boolean;
  additionalContext?: string;
  error?: string;
}

// =============================================================================
// Kanban Board Types
// =============================================================================

export type KanbanColumn = 'todo' | 'inProgress' | 'done';

export interface KanbanCard {
  id: string;
  feature: Feature;
  column: KanbanColumn;
  projectDir: string;
  agent?: string;
  updatedAt: string;
}

export interface KanbanBoard {
  todo: KanbanCard[];
  inProgress: KanbanCard[];
  done: KanbanCard[];
}

// =============================================================================
// Utility Types
// =============================================================================

export type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P];
};

export type WithTimestamps<T> = T & {
  createdAt: string;
  updatedAt: string;
};
