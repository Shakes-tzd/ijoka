<script setup lang="ts">
interface AgentEvent {
  id: number
  eventType: string
  sourceAgent: string
  sessionId: string
  projectDir: string
  toolName?: string
  payload?: string
  featureId?: string
  createdAt: string
}

defineProps<{
  events: AgentEvent[]
}>()

const emit = defineEmits<{
  'event-click': [event: AgentEvent]
}>()

const eventIcons: Record<string, string> = {
  SessionStart: '🚀',
  SessionEnd: '🏁',
  ToolUse: '🔧',
  FeatureStarted: '📝',
  FeatureCompleted: '✅',
  Error: '❌',
  Progress: '📊',
  TranscriptUpdated: '📄',
}

const agentColors: Record<string, string> = {
  'claude-code': '#60a5fa',
  'codex-cli': '#4ade80',
  'gemini-cli': '#fbbf24',
  'hook': '#a78bfa',
  'file-watch': '#64748b',
  'unknown': '#888',
}

function getEventIcon(eventType: string): string {
  return eventIcons[eventType] || '📌'
}

function getAgentColor(agent: string): string {
  return agentColors[agent] || '#888'
}

function formatTime(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatEventType(eventType: string): string {
  return eventType.replace(/([A-Z])/g, ' $1').trim()
}

function getProjectName(projectDir: string): string {
  if (!projectDir) return ''
  const parts = projectDir.split('/')
  return parts[parts.length - 1] || projectDir
}
</script>

<template>
  <div class="activity-timeline">
    <div class="timeline-header">
      <h2>Activity</h2>
    </div>
    
    <div class="timeline-content">
      <div
        v-for="event in events"
        :key="event.id"
        class="timeline-item"
        @click="emit('event-click', event)"
      >
        <div class="timeline-icon">
          {{ getEventIcon(event.eventType) }}
        </div>
        
        <div class="timeline-body">
          <div class="timeline-meta">
            <span
              class="agent-name"
              :style="{ color: getAgentColor(event.sourceAgent) }"
            >
              {{ event.sourceAgent }}
            </span>
            <span class="event-time">{{ formatTime(event.createdAt) }}</span>
          </div>
          
          <p class="event-description">
            {{ formatEventType(event.eventType) }}
            <span v-if="event.toolName" class="tool-name">: {{ event.toolName }}</span>
          </p>
          
          <p v-if="event.projectDir" class="project-name">
            📁 {{ getProjectName(event.projectDir) }}
          </p>
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
  border-bottom: 1px solid var(--border-color);
}

.timeline-header h2 {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.timeline-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.timeline-item {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  transition: background 0.2s;
  cursor: pointer;
}

.timeline-item:hover {
  background: var(--bg-tertiary);
}

.timeline-item:active {
  background: var(--card-bg);
}

.timeline-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 0.9rem;
}

.timeline-body {
  flex: 1;
  min-width: 0;
}

.timeline-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.agent-name {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.event-time {
  font-size: 0.7rem;
  color: var(--text-muted);
}

.event-description {
  font-size: 0.85rem;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.tool-name {
  color: var(--accent-purple);
}

.project-name {
  font-size: 0.7rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
