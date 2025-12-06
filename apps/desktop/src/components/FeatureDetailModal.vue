<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { invoke } from '@tauri-apps/api/core'

interface Feature {
  id: string
  projectDir: string
  description: string
  category: string
  passes: boolean
  inProgress: boolean
  agent?: string
  updatedAt: string
}

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

const props = defineProps<{
  feature: Feature | null
}>()

const emit = defineEmits<{
  close: []
}>()

const events = ref<AgentEvent[]>([])
const loading = ref(false)

const categoryColors: Record<string, string> = {
  functional: '#60a5fa',
  ui: '#a78bfa',
  security: '#f87171',
  performance: '#fbbf24',
  documentation: '#4ade80',
  testing: '#fb923c',
  infrastructure: '#64748b',
  refactoring: '#e879f9',
}

function getCategoryColor(category: string): string {
  return categoryColors[category] || '#888'
}

function formatTime(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString()
}

function getEventIcon(eventType: string): string {
  const icons: Record<string, string> = {
    'ToolUse': '🔧',
    'ToolResult': '📤',
    'SessionStart': '🚀',
    'SessionEnd': '🏁',
    'FeatureCompleted': '✅',
    'Error': '❌',
  }
  return icons[eventType] || '📝'
}

function getStatusBadge(feature: Feature): { text: string; class: string } {
  if (feature.passes) return { text: 'Completed', class: 'status-done' }
  if (feature.inProgress) return { text: 'In Progress', class: 'status-progress' }
  return { text: 'To Do', class: 'status-todo' }
}

async function loadEvents() {
  if (!props.feature) return

  loading.value = true
  try {
    events.value = await invoke<AgentEvent[]>('get_feature_events', {
      featureId: props.feature.id,
      limit: 100
    })
  } catch (e) {
    console.error('Failed to load feature events:', e)
    events.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.feature, (newFeature) => {
  if (newFeature) {
    loadEvents()
  } else {
    events.value = []
  }
}, { immediate: true })

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <div v-if="feature" class="modal-overlay" @click.self="emit('close')">
      <div class="modal-content">
        <div class="modal-header">
          <div class="header-left">
            <span
              class="category-badge"
              :style="{ backgroundColor: getCategoryColor(feature.category) + '20', color: getCategoryColor(feature.category) }"
            >
              {{ feature.category }}
            </span>
            <span :class="['status-badge', getStatusBadge(feature).class]">
              {{ getStatusBadge(feature).text }}
            </span>
          </div>
          <button class="close-btn" @click="emit('close')">×</button>
        </div>

        <div class="modal-body">
          <h2 class="feature-title">{{ feature.description }}</h2>

          <div class="feature-meta">
            <div class="meta-item">
              <span class="meta-label">ID:</span>
              <code class="meta-value">{{ feature.id }}</code>
            </div>
            <div v-if="feature.agent" class="meta-item">
              <span class="meta-label">Agent:</span>
              <span class="meta-value">{{ feature.agent }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Updated:</span>
              <span class="meta-value">{{ formatTime(feature.updatedAt) }}</span>
            </div>
          </div>

          <div class="events-section">
            <h3 class="section-title">Activity History</h3>

            <div v-if="loading" class="events-loading">
              Loading activities...
            </div>

            <div v-else-if="events.length === 0" class="events-empty">
              <p>No activities linked to this feature yet.</p>
              <p class="events-hint">Activities will appear here when events are sent with this feature's ID.</p>
            </div>

            <div v-else class="events-list">
              <div
                v-for="event in events"
                :key="event.id"
                class="event-item"
              >
                <span class="event-icon">{{ getEventIcon(event.eventType) }}</span>
                <div class="event-content">
                  <div class="event-header">
                    <span class="event-type">{{ event.eventType }}</span>
                    <span class="event-time">{{ formatTime(event.createdAt) }}</span>
                  </div>
                  <div class="event-details">
                    <span class="event-agent">{{ event.sourceAgent }}</span>
                    <span v-if="event.toolName" class="event-tool">{{ event.toolName }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 20px;
}

.modal-content {
  background: var(--bg-secondary);
  border-radius: 12px;
  width: 100%;
  max-width: 600px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
  border: 1px solid var(--border-color);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
}

.header-left {
  display: flex;
  gap: 10px;
  align-items: center;
}

.category-badge {
  font-size: 0.75rem;
  padding: 4px 10px;
  border-radius: 4px;
  font-weight: 500;
  text-transform: uppercase;
}

.status-badge {
  font-size: 0.75rem;
  padding: 4px 10px;
  border-radius: 4px;
  font-weight: 500;
}

.status-done {
  background: rgba(74, 222, 128, 0.2);
  color: var(--accent-green);
}

.status-progress {
  background: rgba(251, 191, 36, 0.2);
  color: var(--accent-yellow);
}

.status-todo {
  background: rgba(96, 165, 250, 0.2);
  color: var(--accent-blue);
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 1.5rem;
  cursor: pointer;
  padding: 4px 8px;
  line-height: 1;
  border-radius: 4px;
  transition: all 0.2s;
}

.close-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.feature-title {
  font-size: 1.25rem;
  font-weight: 600;
  margin-bottom: 16px;
  line-height: 1.4;
}

.feature-meta {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 24px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.meta-item {
  display: flex;
  gap: 8px;
  font-size: 0.85rem;
}

.meta-label {
  color: var(--text-secondary);
  min-width: 60px;
}

.meta-value {
  color: var(--text-primary);
}

.meta-value code {
  font-family: monospace;
  background: var(--bg-primary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.8rem;
}

.events-section {
  border-top: 1px solid var(--border-color);
  padding-top: 20px;
}

.section-title {
  font-size: 0.95rem;
  font-weight: 600;
  margin-bottom: 16px;
  color: var(--text-secondary);
}

.events-loading,
.events-empty {
  text-align: center;
  padding: 24px;
  color: var(--text-secondary);
}

.events-hint {
  font-size: 0.8rem;
  margin-top: 8px;
  color: var(--text-muted);
}

.events-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.event-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.event-icon {
  font-size: 1.25rem;
  flex-shrink: 0;
}

.event-content {
  flex: 1;
  min-width: 0;
}

.event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.event-type {
  font-weight: 500;
  font-size: 0.9rem;
}

.event-time {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.event-details {
  display: flex;
  gap: 8px;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.event-tool {
  padding: 2px 6px;
  background: var(--bg-secondary);
  border-radius: 4px;
}
</style>
