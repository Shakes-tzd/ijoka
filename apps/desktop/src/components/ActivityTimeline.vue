<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import ToolIcon from './icons/ToolIcon.vue'
import ActivityCard from './ActivityCard.vue'

interface AgentEvent {
  id: number
  eventType: string
  sourceAgent: string
  sessionId: string
  projectDir: string
  toolName?: string
  payload?: string | object
  featureId?: string
  createdAt: string
}

interface SessionGroup {
  sessionId: string
  sourceAgent: string
  projectDir: string
  startTime: string
  endTime: string | null
  events: AgentEvent[]
  isActive: boolean
}

const props = defineProps<{
  events: AgentEvent[]
}>()

// Track collapsed sessions (collapsed by default for ended sessions)
const collapsedSessions = ref<Set<string>>(new Set())

// Session is considered stale after 15 minutes of inactivity
const STALE_SESSION_MINUTES = 15

// Group events by sessionId
const sessionGroups = computed<SessionGroup[]>(() => {
  const groups = new Map<string, SessionGroup>()
  const now = new Date()

  // Sort events by time (oldest first for grouping)
  const sortedEvents = [...props.events].sort((a, b) =>
    new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()
  )

  for (const event of sortedEvents) {
    const sessionId = event.sessionId || 'unknown'

    if (!groups.has(sessionId)) {
      groups.set(sessionId, {
        sessionId,
        sourceAgent: event.sourceAgent,
        projectDir: event.projectDir,
        startTime: event.createdAt,
        endTime: null,
        events: [],
        isActive: true
      })
    }

    const group = groups.get(sessionId)!
    group.events.push(event)

    // Update end time and status
    if (event.eventType === 'SessionEnd') {
      group.endTime = event.createdAt
      group.isActive = false
    }

    // Track latest activity time
    const eventTime = new Date(event.createdAt)
    if (eventTime > new Date(group.startTime)) {
      if (!group.endTime || group.isActive) {
        // Update "last activity" for active sessions
        group.endTime = event.createdAt
      }
    }
  }

  // Mark stale sessions as inactive (no activity for 30+ minutes)
  // Also reverse events so latest appears at top
  for (const group of groups.values()) {
    // Reverse events order: latest activity at top
    group.events.reverse()

    if (group.isActive) {
      const lastActivity = group.endTime ? new Date(group.endTime) : new Date(group.startTime)
      const minutesSinceActivity = (now.getTime() - lastActivity.getTime()) / (1000 * 60)

      if (minutesSinceActivity > STALE_SESSION_MINUTES) {
        group.isActive = false
      }
    }
  }

  // Identify internal/subagent sessions (e.g., feature classifier, prompt enhancement)
  const isInternalSession = (group: SessionGroup): boolean => {
    // Short sessions (≤6 events) that look like automated subagent calls
    if (group.events.length <= 6) {
      // Check for automated/internal prompt patterns
      const hasInternalPrompt = group.events.some(e => {
        if (e.eventType === 'UserQuery' && e.payload) {
          try {
            // Handle both string (from SQLite) and object (from Memgraph)
            const payload = typeof e.payload === 'string' ? JSON.parse(e.payload) : e.payload
            const prompt = (payload.prompt || payload.preview || '').toLowerCase()
            // Patterns that indicate internal/automated sessions
            return prompt.includes('feature classifier') ||
                   prompt.includes('you are a feature classifier') ||
                   prompt.includes('prompt enhancement') ||
                   prompt.includes('you are a prompt enhancement') ||
                   prompt.includes('classify the following') ||
                   prompt.includes('analyze the following') ||
                   prompt.startsWith('you are a') || // Common system prompt pattern
                   prompt.startsWith('as a') // Another system prompt pattern
          } catch { return false }
        }
        return false
      })

      // Also check if it's a very short session with only lifecycle events
      const hasOnlyLifecycleEvents = group.events.every(e =>
        ['SessionStart', 'SessionEnd', 'AgentStop', 'SubagentStop', 'UserQuery'].includes(e.eventType)
      )

      // Sessions that are short AND (have internal prompts OR only lifecycle events)
      if (hasInternalPrompt) return true
      if (group.events.length <= 4 && hasOnlyLifecycleEvents) return true
    }
    return false
  }

  // Separate internal sessions and combine them into one group
  const allGroups = Array.from(groups.values())
  const regularSessions = allGroups.filter(g => !isInternalSession(g))
  const internalSessions = allGroups.filter(g => isInternalSession(g))

  // If there are internal sessions, combine them into a single "Subagents" group
  if (internalSessions.length > 0) {
    const combinedInternal: SessionGroup = {
      sessionId: 'internal-subagents',
      sourceAgent: 'subagents',
      projectDir: internalSessions[0].projectDir,
      startTime: internalSessions.reduce((min, s) =>
        new Date(s.startTime) < new Date(min) ? s.startTime : min,
        internalSessions[0].startTime
      ),
      endTime: internalSessions.reduce((max, s) => {
        const sEnd = s.endTime || s.startTime
        return new Date(sEnd) > new Date(max) ? sEnd : max
      }, internalSessions[0].endTime || internalSessions[0].startTime),
      events: internalSessions.flatMap(s => s.events),
      isActive: internalSessions.some(s => s.isActive)
    }
    // Sort combined events by time (latest first)
    combinedInternal.events.sort((a, b) =>
      new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    )
    regularSessions.push(combinedInternal)
  }

  // Sort: active first, then by most recent activity
  return regularSessions.sort((a, b) => {
      // Active sessions first
      if (a.isActive !== b.isActive) {
        return a.isActive ? -1 : 1
      }
      // Then sort by most recent activity
      const aTime = a.endTime ? new Date(a.endTime) : new Date(a.startTime)
      const bTime = b.endTime ? new Date(b.endTime) : new Date(b.startTime)
      return bTime.getTime() - aTime.getTime()
    })
})

// Auto-collapse internal/subagent sessions
watch(sessionGroups, (groups) => {
  for (const group of groups) {
    // Auto-collapse internal-subagents group
    if (group.sessionId === 'internal-subagents' && !collapsedSessions.value.has('internal-subagents')) {
      collapsedSessions.value.add('internal-subagents')
    }
  }
}, { immediate: true })

function toggleSession(sessionId: string) {
  if (collapsedSessions.value.has(sessionId)) {
    collapsedSessions.value.delete(sessionId)
  } else {
    collapsedSessions.value.add(sessionId)
  }
}

function isCollapsed(sessionId: string): boolean {
  // Internal subagents are collapsed by default
  if (sessionId === 'internal-subagents') {
    return collapsedSessions.value.has(sessionId)
  }
  return collapsedSessions.value.has(sessionId)
}

function formatDuration(startTime: string, endTime: string | null): string {
  const start = new Date(startTime)
  const end = endTime ? new Date(endTime) : new Date()
  const diffMs = Math.abs(end.getTime() - start.getTime())

  const totalSeconds = Math.floor(diffMs / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60

  if (hours > 0) {
    return `${hours}h ${minutes}m`
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`
  }
  return `${seconds}s`
}

function getShortSessionId(sessionId: string): string {
  // Show last 8 chars of session ID
  if (sessionId.length > 12) {
    return '...' + sessionId.slice(-8)
  }
  return sessionId
}

function getProjectName(projectDir: string): string {
  if (!projectDir) return 'unknown'
  // Extract last segment of path as project name
  const segments = projectDir.replace(/\/$/, '').split('/')
  return segments[segments.length - 1] || 'unknown'
}

const emit = defineEmits<{
  'event-click': [event: AgentEvent]
}>()

// Agent colors for session header (still needed here)
const agentColors: Record<string, string> = {
  'claude-code': '#60a5fa',
  'codex-cli': '#4ade80',
  'gemini-cli': '#fbbf24',
  'hook': '#a78bfa',
  'file-watch': '#64748b',
  'subagents': '#94a3b8',
  'unknown': '#888',
}

function getAgentColor(agent: string): string {
  return agentColors[agent] || '#888'
}
</script>

<template>
  <div class="activity-timeline">
    <div class="timeline-header">
      <h2>Activity</h2>
      <span class="session-count">{{ sessionGroups.length }} sessions</span>
    </div>

    <div class="timeline-content">
      <!-- Session groups -->
      <div
        v-for="session in sessionGroups"
        :key="session.sessionId"
        class="session-group"
        :class="{ 'session-active': session.isActive }"
      >
        <!-- Session header (clickable to expand/collapse) -->
        <div
          class="session-header"
          @click="toggleSession(session.sessionId)"
        >
          <!-- Row 1: Agent + Status -->
          <div class="session-row-primary">
            <div class="session-agent-info">
              <ToolIcon
                :name="isCollapsed(session.sessionId) ? 'chevron-right' : 'chevron-down'"
                :size="12"
                class="collapse-icon"
              />
              <span
                class="agent-dot"
                :style="{ background: getAgentColor(session.sourceAgent) }"
              ></span>
              <span class="session-agent">
                {{ session.sessionId === 'internal-subagents' ? 'Internal Tasks' : session.sourceAgent }}
              </span>
            </div>
            <span v-if="session.sessionId === 'internal-subagents'" class="session-status internal">auto</span>
            <span v-else-if="session.isActive" class="session-status active">active</span>
            <span v-else class="session-status ended">ended</span>
          </div>
          <!-- Row 2: Project + Stats -->
          <div class="session-row-secondary">
            <div class="session-info-left">
              <span class="session-project">{{ getProjectName(session.projectDir) }}</span>
              <span class="session-separator">·</span>
              <span v-if="session.sessionId === 'internal-subagents'" class="session-id">classifiers & helpers</span>
              <span v-else class="session-id">{{ getShortSessionId(session.sessionId) }}</span>
            </div>
            <div class="session-meta">
              <span class="session-stats">{{ session.events.length }}</span>
              <span class="session-duration">{{ formatDuration(session.startTime, session.endTime) }}</span>
            </div>
          </div>
        </div>

        <!-- Session events (collapsible) -->
        <div v-show="!isCollapsed(session.sessionId)" class="session-events">
          <ActivityCard
            v-for="event in session.events"
            :key="event.id"
            :event="event"
            :show-feature-link="true"
            @click="emit('event-click', event)"
          />
        </div>
      </div>

      <div v-if="events.length === 0" class="empty-timeline">
        <p>No activity yet</p>
        <p class="hint">Events will appear here as agents work</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.activity-timeline {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.timeline-header {
  padding: 16px;
  padding-left: 44px; /* Clear the sidebar toggle button */
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.timeline-header h2 {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.session-count {
  font-size: 0.75rem;
  color: var(--text-muted);
}

/* Session group styles */
.session-group {
  border-bottom: 1px solid var(--border-color);
}

.session-group:last-child {
  border-bottom: none;
}

.session-group.session-active {
  background: rgba(96, 165, 250, 0.03);
}

.session-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 12px;
  cursor: pointer;
  background: var(--bg-secondary);
  transition: background 0.15s;
}

.session-header:hover {
  background: var(--bg-tertiary);
}

/* Row 1: Agent + Status */
.session-row-primary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.session-agent-info {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.collapse-icon {
  color: var(--text-muted);
  flex-shrink: 0;
}

.session-agent {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}

/* Row 2: ID + Stats */
.session-row-secondary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding-left: 18px;
}

.session-info-left {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.session-project {
  font-size: 0.7rem;
  color: var(--text-secondary);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-separator {
  font-size: 0.65rem;
  color: var(--text-muted);
}

.session-id {
  font-size: 0.65rem;
  color: var(--text-muted);
  font-family: monospace;
  white-space: nowrap;
}

.session-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.session-stats {
  font-size: 0.65rem;
  color: var(--text-muted);
}

.session-stats::after {
  content: ' events';
}

.session-duration {
  font-size: 0.65rem;
  color: var(--text-secondary);
  font-family: monospace;
}

.session-status {
  font-size: 0.6rem;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.02em;
  flex-shrink: 0;
}

.session-status.active {
  background: rgba(96, 165, 250, 0.2);
  color: #60a5fa;
}

.session-status.ended {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.session-status.internal {
  background: rgba(148, 163, 184, 0.2);
  color: #94a3b8;
  font-style: italic;
}

.session-events {
  padding: 4px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.timeline-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.empty-timeline {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--text-muted);
}

.empty-timeline p {
  font-size: 0.85rem;
}

.empty-timeline .hint {
  font-size: 0.75rem;
  margin-top: 4px;
}
</style>
