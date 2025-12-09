<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import ActivityCard from './ActivityCard.vue'

interface Feature {
  id: string
  projectDir: string
  description: string
  category: string
  passes: boolean
  inProgress: boolean
  agent?: string
  steps?: string[]
  updatedAt: string
}

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

const props = defineProps<{
  feature: Feature | null
}>()

const emit = defineEmits<{
  close: []
}>()

const events = ref<AgentEvent[]>([])
const loading = ref(false)
const expandedEvents = ref<Set<number>>(new Set())

function toggleExpand(eventId: number) {
  if (expandedEvents.value.has(eventId)) {
    expandedEvents.value.delete(eventId)
  } else {
    expandedEvents.value.add(eventId)
  }
}

function isExpanded(eventId: number): boolean {
  return expandedEvents.value.has(eventId)
}

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

interface ParsedPayload {
  inputSummary?: string
  filePaths?: string[]
  success?: boolean
  featureDescription?: string
  messageType?: string
  preview?: string
  // Tool-specific fields
  command?: string
  description?: string
  outputPreview?: string
  filePath?: string
  oldString?: string
  newString?: string
  contentPreview?: string
  pattern?: string
  path?: string
  glob?: string
  offset?: number
  limit?: number
  [key: string]: unknown
}

function parsePayload(payload?: string | object): ParsedPayload | null {
  if (!payload) return null
  // Handle both string (from SQLite) and object (from Memgraph)
  if (typeof payload === 'object') {
    return payload as ParsedPayload
  }
  try {
    return JSON.parse(payload)
  } catch {
    return null
  }
}

function getSuccessClass(success?: boolean): string {
  if (success === true) return 'success'
  if (success === false) return 'failure'
  return ''
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

          <!-- Steps checklist -->
          <div v-if="feature.steps?.length" class="steps-section">
            <h3 class="section-title">Verification Steps</h3>
            <ul class="steps-list">
              <li
                v-for="(step, idx) in feature.steps"
                :key="idx"
                class="step-item"
                :class="{ 'step-complete': feature.passes }"
              >
                <span class="step-checkbox">{{ feature.passes ? '✓' : '○' }}</span>
                <span class="step-text">{{ step }}</span>
              </li>
            </ul>
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
                class="event-wrapper"
                :class="[
                  getSuccessClass(parsePayload(event.payload)?.success),
                  { 'expanded': isExpanded(event.id) }
                ]"
              >
                <!-- Base card using shared component -->
                <ActivityCard
                  :event="event"
                  :expanded="isExpanded(event.id)"
                  @click="toggleExpand(event.id)"
                />

                <!-- Expand indicator -->
                <span class="expand-icon" @click="toggleExpand(event.id)">
                  {{ isExpanded(event.id) ? '▼' : '▶' }}
                </span>

                <!-- Expanded content (modal-specific details) -->
                <div v-if="isExpanded(event.id)" class="event-expanded">
                  <!-- Bash tool details -->
                  <div v-if="event.toolName === 'Bash' && parsePayload(event.payload)?.command" class="tool-detail">
                    <div class="detail-label">Command:</div>
                    <pre class="detail-code">{{ parsePayload(event.payload)?.command }}</pre>
                    <div v-if="parsePayload(event.payload)?.outputPreview" class="detail-section">
                      <div class="detail-label">Output:</div>
                      <pre class="detail-output">{{ parsePayload(event.payload)?.outputPreview }}</pre>
                    </div>
                  </div>
                  <!-- Edit tool details -->
                  <div v-else-if="event.toolName === 'Edit'" class="tool-detail">
                    <div class="detail-label">File: <code>{{ parsePayload(event.payload)?.filePath }}</code></div>
                    <div v-if="parsePayload(event.payload)?.oldString" class="detail-section">
                      <div class="detail-label">Old:</div>
                      <pre class="detail-code diff-old">{{ parsePayload(event.payload)?.oldString }}</pre>
                    </div>
                    <div v-if="parsePayload(event.payload)?.newString" class="detail-section">
                      <div class="detail-label">New:</div>
                      <pre class="detail-code diff-new">{{ parsePayload(event.payload)?.newString }}</pre>
                    </div>
                  </div>
                  <!-- Read tool details -->
                  <div v-else-if="event.toolName === 'Read'" class="tool-detail">
                    <div class="detail-label">File: <code>{{ parsePayload(event.payload)?.filePath }}</code></div>
                    <div v-if="parsePayload(event.payload)?.offset !== undefined" class="detail-meta">
                      Lines {{ parsePayload(event.payload)?.offset }} - {{ (parsePayload(event.payload)?.offset || 0) + (parsePayload(event.payload)?.limit || 0) }}
                    </div>
                  </div>
                  <!-- Grep tool details -->
                  <div v-else-if="event.toolName === 'Grep'" class="tool-detail">
                    <div class="detail-label">Pattern: <code>{{ parsePayload(event.payload)?.pattern }}</code></div>
                    <div v-if="parsePayload(event.payload)?.path" class="detail-meta">Path: {{ parsePayload(event.payload)?.path }}</div>
                    <div v-if="parsePayload(event.payload)?.glob" class="detail-meta">Glob: {{ parsePayload(event.payload)?.glob }}</div>
                  </div>
                  <!-- Glob tool details -->
                  <div v-else-if="event.toolName === 'Glob'" class="tool-detail">
                    <div class="detail-label">Pattern: <code>{{ parsePayload(event.payload)?.pattern }}</code></div>
                    <div v-if="parsePayload(event.payload)?.path" class="detail-meta">Path: {{ parsePayload(event.payload)?.path }}</div>
                  </div>
                  <!-- Default: show summary/preview -->
                  <div v-else>
                    <div v-if="parsePayload(event.payload)?.inputSummary" class="event-summary">
                      {{ parsePayload(event.payload)?.inputSummary }}
                    </div>
                    <div v-else-if="parsePayload(event.payload)?.preview" class="event-summary">
                      {{ parsePayload(event.payload)?.preview }}
                    </div>
                  </div>
                  <!-- Files list -->
                  <div v-if="parsePayload(event.payload)?.filePaths?.length" class="event-files">
                    <span class="files-label">Files:</span>
                    <div class="files-list">
                      <span
                        v-for="(file, idx) in parsePayload(event.payload)?.filePaths"
                        :key="idx"
                        class="file-path"
                      >
                        {{ file }}
                      </span>
                    </div>
                  </div>
                  <!-- Raw payload toggle -->
                  <div v-if="event.payload" class="event-raw" @click.stop>
                    <details>
                      <summary>Raw payload</summary>
                      <pre>{{ JSON.stringify(parsePayload(event.payload), null, 2) }}</pre>
                    </details>
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

.steps-section {
  margin-bottom: 20px;
}

.steps-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.step-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  margin-bottom: 6px;
  align-items: flex-start;
}

.step-item.step-complete {
  opacity: 0.7;
}

.step-checkbox {
  font-size: 1rem;
  color: var(--text-muted);
  flex-shrink: 0;
}

.step-complete .step-checkbox {
  color: var(--accent-green);
}

.step-text {
  font-size: 0.85rem;
  line-height: 1.4;
  color: var(--text-primary);
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
  gap: 16px;
}

.event-wrapper {
  position: relative;
  border-radius: 10px;
  overflow: hidden;
  background: var(--card-bg);
  border: 1px solid var(--border-color);
}

.event-wrapper.expanded {
  background: var(--bg-secondary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.event-wrapper.success {
  border-left: 3px solid var(--accent-green);
}

.event-wrapper.failure {
  border-left: 3px solid #f87171;
}

/* Override ActivityCard styles when inside wrapper */
.event-wrapper :deep(.activity-card) {
  border-radius: 0;
  background: transparent;
}

.event-wrapper :deep(.activity-card:hover) {
  background: rgba(255, 255, 255, 0.02);
}

.expand-icon {
  position: absolute;
  top: 12px;
  right: 12px;
  font-size: 0.6rem;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  z-index: 1;
}

.expand-icon:hover {
  color: var(--text-primary);
}

.event-expanded {
  padding: 14px 16px;
  background: var(--bg-tertiary);
  border-top: 1px solid var(--border-color);
}

.event-summary {
  margin-top: 6px;
  font-size: 0.8rem;
  color: var(--text-primary);
  padding: 10px 12px;
  background: var(--bg-primary);
  border-radius: 6px;
  font-family: monospace;
  word-break: break-word;
  line-height: 1.4;
}

.event-files {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.files-label {
  font-size: 0.7rem;
  color: var(--text-muted);
}

.file-path {
  font-size: 0.7rem;
  padding: 2px 6px;
  background: var(--bg-secondary);
  border-radius: 4px;
  color: var(--accent-blue);
  font-family: monospace;
}

.more-files {
  font-size: 0.7rem;
  color: var(--text-muted);
}

.truncate {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.event-expanded .event-summary {
  white-space: pre-wrap;
  max-height: 300px;
  overflow-y: auto;
}

.event-expanded .files-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.event-expanded .file-path {
  display: block;
  word-break: break-all;
}

.event-raw {
  margin-top: 12px;
}

.event-raw summary {
  font-size: 0.75rem;
  color: var(--text-muted);
  cursor: pointer;
}

.event-raw pre {
  margin-top: 8px;
  padding: 8px;
  background: var(--bg-primary);
  border-radius: 4px;
  font-size: 0.7rem;
  overflow-x: auto;
  max-height: 200px;
  overflow-y: auto;
}

/* Tool-specific detail styles */
.tool-detail {
  margin-top: 0;
}

.detail-label {
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.detail-label code {
  color: var(--accent-blue);
  background: var(--bg-primary);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.75rem;
}

.detail-section {
  margin-top: 8px;
}

.detail-meta {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 4px;
}

.detail-code {
  margin: 6px 0;
  padding: 10px 12px;
  background: var(--bg-primary);
  border-radius: 6px;
  font-size: 0.75rem;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 150px;
  overflow-y: auto;
}

.detail-output {
  margin: 6px 0;
  padding: 10px 12px;
  background: var(--bg-primary);
  border-radius: 6px;
  font-size: 0.7rem;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  color: var(--text-secondary);
}

.diff-old {
  border-left: 3px solid #f87171;
}

.diff-new {
  border-left: 3px solid var(--accent-green);
}
</style>
