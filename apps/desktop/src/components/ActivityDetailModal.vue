<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'

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
  event: AgentEvent | null
}>()

const emit = defineEmits<{
  close: []
}>()

const agentColors: Record<string, string> = {
  'claude-code': '#60a5fa',
  'codex-cli': '#4ade80',
  'gemini-cli': '#fbbf24',
  'hook': '#a78bfa',
  'file-watch': '#64748b',
  'unknown': '#888',
}

function getAgentColor(agent: string): string {
  return agentColors[agent] || '#888'
}

function formatTime(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleString()
}

function getEventIcon(eventType: string): string {
  const icons: Record<string, string> = {
    'ToolUse': '🔧',
    'ToolCall': '🔧',
    'ToolResult': '📤',
    'SessionStart': '🚀',
    'SessionEnd': '🏁',
    'FeatureCompleted': '✅',
    'Error': '❌',
    'TranscriptUpdated': '💬',
    'AgentStop': '🛑',
    'SubagentStop': '🤖',
  }
  return icons[eventType] || '📝'
}

function getProjectName(projectDir: string): string {
  if (!projectDir) return ''
  const parts = projectDir.split('/')
  return parts[parts.length - 1] || projectDir
}

interface ParsedPayload {
  inputSummary?: string
  filePaths?: string[]
  success?: boolean
  featureDescription?: string
  messageType?: string
  preview?: string
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
  taskDescription?: string
  subagentType?: string
  resultSummary?: string
  reason?: string
  lastMessage?: string
  // New ToolResult fields
  toolUseId?: string
  isError?: boolean
  // Tool use fields from transcript
  tool?: string
  inputPreview?: string
  [key: string]: unknown
}

function parsePayload(payload?: string): ParsedPayload | null {
  if (!payload) return null
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
    <div v-if="event" class="modal-overlay" @click.self="emit('close')">
      <div class="modal-content">
        <div class="modal-header">
          <div class="header-left">
            <span class="event-icon-large">{{ getEventIcon(event.eventType) }}</span>
            <span class="event-type-badge">{{ event.eventType }}</span>
            <span
              v-if="parsePayload(event.payload)?.success !== undefined"
              :class="['status-badge', parsePayload(event.payload)?.success ? 'status-success' : 'status-error']"
            >
              {{ parsePayload(event.payload)?.success ? 'Success' : 'Failed' }}
            </span>
          </div>
          <button class="close-btn" @click="emit('close')">×</button>
        </div>

        <div class="modal-body">
          <!-- Event metadata -->
          <div class="event-meta">
            <div class="meta-item">
              <span class="meta-label">Agent:</span>
              <span class="meta-value agent-name" :style="{ color: getAgentColor(event.sourceAgent) }">
                {{ event.sourceAgent }}
              </span>
            </div>
            <div v-if="event.toolName" class="meta-item">
              <span class="meta-label">Tool:</span>
              <span class="meta-value tool-name">{{ event.toolName }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">Time:</span>
              <span class="meta-value">{{ formatTime(event.createdAt) }}</span>
            </div>
            <div v-if="event.projectDir" class="meta-item">
              <span class="meta-label">Project:</span>
              <span class="meta-value">{{ getProjectName(event.projectDir) }}</span>
            </div>
            <div v-if="event.featureId" class="meta-item">
              <span class="meta-label">Feature:</span>
              <code class="meta-value">{{ event.featureId }}</code>
            </div>
            <div class="meta-item">
              <span class="meta-label">Session:</span>
              <code class="meta-value session-id">{{ event.sessionId }}</code>
            </div>
          </div>

          <!-- Tool-specific content -->
          <div class="tool-content" :class="getSuccessClass(parsePayload(event.payload)?.success)">
            <!-- Bash tool -->
            <div v-if="event.toolName === 'Bash' && parsePayload(event.payload)" class="tool-detail">
              <div v-if="parsePayload(event.payload)?.description" class="detail-description">
                {{ parsePayload(event.payload)?.description }}
              </div>
              <div v-if="parsePayload(event.payload)?.command" class="detail-section">
                <div class="detail-label">Command:</div>
                <pre class="detail-code">{{ parsePayload(event.payload)?.command }}</pre>
              </div>
              <div v-if="parsePayload(event.payload)?.outputPreview" class="detail-section">
                <div class="detail-label">Output:</div>
                <pre class="detail-output">{{ parsePayload(event.payload)?.outputPreview }}</pre>
              </div>
            </div>

            <!-- Edit tool -->
            <div v-else-if="event.toolName === 'Edit' && parsePayload(event.payload)" class="tool-detail">
              <div class="detail-section">
                <div class="detail-label">File:</div>
                <code class="file-path-full">{{ parsePayload(event.payload)?.filePath }}</code>
              </div>
              <div v-if="parsePayload(event.payload)?.oldString" class="detail-section">
                <div class="detail-label">Removed:</div>
                <pre class="detail-code diff-old">{{ parsePayload(event.payload)?.oldString }}</pre>
              </div>
              <div v-if="parsePayload(event.payload)?.newString" class="detail-section">
                <div class="detail-label">Added:</div>
                <pre class="detail-code diff-new">{{ parsePayload(event.payload)?.newString }}</pre>
              </div>
            </div>

            <!-- Write tool -->
            <div v-else-if="event.toolName === 'Write' && parsePayload(event.payload)" class="tool-detail">
              <div class="detail-section">
                <div class="detail-label">File:</div>
                <code class="file-path-full">{{ parsePayload(event.payload)?.filePath }}</code>
              </div>
              <div v-if="parsePayload(event.payload)?.contentPreview" class="detail-section">
                <div class="detail-label">Content Preview:</div>
                <pre class="detail-code">{{ parsePayload(event.payload)?.contentPreview }}</pre>
              </div>
            </div>

            <!-- Read tool -->
            <div v-else-if="event.toolName === 'Read' && parsePayload(event.payload)" class="tool-detail">
              <div class="detail-section">
                <div class="detail-label">File:</div>
                <code class="file-path-full">{{ parsePayload(event.payload)?.filePath }}</code>
              </div>
              <div v-if="parsePayload(event.payload)?.offset !== undefined" class="detail-meta">
                Lines {{ parsePayload(event.payload)?.offset }} - {{ (parsePayload(event.payload)?.offset || 0) + (parsePayload(event.payload)?.limit || 0) }}
              </div>
            </div>

            <!-- Grep tool -->
            <div v-else-if="event.toolName === 'Grep' && parsePayload(event.payload)" class="tool-detail">
              <div class="detail-section">
                <div class="detail-label">Pattern:</div>
                <code class="pattern-code">{{ parsePayload(event.payload)?.pattern }}</code>
              </div>
              <div v-if="parsePayload(event.payload)?.path" class="detail-meta">Path: {{ parsePayload(event.payload)?.path }}</div>
              <div v-if="parsePayload(event.payload)?.glob" class="detail-meta">Glob: {{ parsePayload(event.payload)?.glob }}</div>
            </div>

            <!-- Glob tool -->
            <div v-else-if="event.toolName === 'Glob' && parsePayload(event.payload)" class="tool-detail">
              <div class="detail-section">
                <div class="detail-label">Pattern:</div>
                <code class="pattern-code">{{ parsePayload(event.payload)?.pattern }}</code>
              </div>
              <div v-if="parsePayload(event.payload)?.path" class="detail-meta">Path: {{ parsePayload(event.payload)?.path }}</div>
            </div>

            <!-- Task (Subagent) tool -->
            <div v-else-if="event.toolName === 'Task' && parsePayload(event.payload)" class="tool-detail">
              <div v-if="parsePayload(event.payload)?.taskDescription" class="detail-section">
                <div class="detail-label">Task:</div>
                <div class="detail-text">{{ parsePayload(event.payload)?.taskDescription }}</div>
              </div>
              <div v-if="parsePayload(event.payload)?.subagentType" class="detail-meta">
                Agent Type: {{ parsePayload(event.payload)?.subagentType }}
              </div>
              <div v-if="parsePayload(event.payload)?.resultSummary" class="detail-section">
                <div class="detail-label">Result:</div>
                <pre class="detail-output">{{ parsePayload(event.payload)?.resultSummary }}</pre>
              </div>
            </div>

            <!-- Agent Stop event -->
            <div v-else-if="event.eventType === 'AgentStop' && parsePayload(event.payload)" class="tool-detail">
              <div v-if="parsePayload(event.payload)?.reason" class="detail-section">
                <div class="detail-label">Reason:</div>
                <div class="detail-text">{{ parsePayload(event.payload)?.reason }}</div>
              </div>
              <div v-if="parsePayload(event.payload)?.lastMessage" class="detail-section">
                <div class="detail-label">Last Message:</div>
                <pre class="detail-output">{{ parsePayload(event.payload)?.lastMessage }}</pre>
              </div>
            </div>

            <!-- Tool Result (from transcript) -->
            <div v-else-if="parsePayload(event.payload)?.messageType === 'tool_result'" class="tool-detail">
              <div v-if="parsePayload(event.payload)?.isError" class="result-error-badge">
                Error
              </div>
              <div v-if="parsePayload(event.payload)?.toolUseId" class="detail-meta">
                Tool Use ID: {{ parsePayload(event.payload)?.toolUseId }}
              </div>
              <div v-if="parsePayload(event.payload)?.preview" class="detail-section">
                <div class="detail-label">Result:</div>
                <pre :class="['detail-output', parsePayload(event.payload)?.isError ? 'error-output' : '']">{{ parsePayload(event.payload)?.preview }}</pre>
              </div>
              <div v-else class="empty-result">
                <span class="empty-icon">📭</span>
                <span>No result content captured</span>
              </div>
            </div>

            <!-- Tool Use from transcript (fallback when no specific handler matched) -->
            <div v-else-if="parsePayload(event.payload)?.messageType === 'tool_use'" class="tool-detail">
              <div class="detail-section">
                <div class="detail-label">Tool: {{ parsePayload(event.payload)?.tool }}</div>
              </div>
              <!-- Show any available fields -->
              <div v-if="parsePayload(event.payload)?.command" class="detail-section">
                <div class="detail-label">Command:</div>
                <pre class="detail-code">{{ parsePayload(event.payload)?.command }}</pre>
              </div>
              <div v-if="parsePayload(event.payload)?.filePath" class="detail-section">
                <div class="detail-label">File:</div>
                <code class="file-path-full">{{ parsePayload(event.payload)?.filePath }}</code>
              </div>
              <div v-if="parsePayload(event.payload)?.pattern" class="detail-section">
                <div class="detail-label">Pattern:</div>
                <code class="pattern-code">{{ parsePayload(event.payload)?.pattern }}</code>
              </div>
              <div v-if="parsePayload(event.payload)?.inputPreview" class="detail-section">
                <div class="detail-label">Input:</div>
                <pre class="detail-code">{{ parsePayload(event.payload)?.inputPreview }}</pre>
              </div>
            </div>

            <!-- Transcript Updated / Messages (other types with preview) -->
            <div v-else-if="parsePayload(event.payload)?.preview" class="tool-detail">
              <div class="detail-section">
                <div class="detail-label">{{ parsePayload(event.payload)?.messageType || 'Content' }}:</div>
                <pre class="detail-output">{{ parsePayload(event.payload)?.preview }}</pre>
              </div>
            </div>

            <!-- Default: show input summary -->
            <div v-else-if="parsePayload(event.payload)?.inputSummary" class="tool-detail">
              <div class="detail-section">
                <div class="detail-label">Summary:</div>
                <div class="detail-text">{{ parsePayload(event.payload)?.inputSummary }}</div>
              </div>
            </div>

            <!-- Files list -->
            <div v-if="parsePayload(event.payload)?.filePaths?.length" class="files-section">
              <div class="detail-label">Files Touched:</div>
              <div class="files-list">
                <code
                  v-for="(file, idx) in parsePayload(event.payload)?.filePaths"
                  :key="idx"
                  class="file-path"
                >
                  {{ file }}
                </code>
              </div>
            </div>
          </div>

          <!-- Raw payload -->
          <div v-if="event.payload" class="raw-section">
            <details>
              <summary>Raw Payload</summary>
              <pre class="raw-json">{{ JSON.stringify(parsePayload(event.payload), null, 2) }}</pre>
            </details>
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
  max-width: 700px;
  max-height: 85vh;
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
  gap: 12px;
  align-items: center;
}

.event-icon-large {
  font-size: 1.5rem;
}

.event-type-badge {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.status-badge {
  font-size: 0.75rem;
  padding: 4px 10px;
  border-radius: 4px;
  font-weight: 500;
}

.status-success {
  background: rgba(74, 222, 128, 0.2);
  color: var(--accent-green);
}

.status-error {
  background: rgba(248, 113, 113, 0.2);
  color: #f87171;
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

.event-meta {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 20px;
  padding: 16px;
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
  word-break: break-all;
}

.agent-name {
  font-weight: 600;
  text-transform: uppercase;
  font-size: 0.8rem;
}

.tool-name {
  background: var(--accent-purple);
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.8rem;
}

.session-id {
  font-family: monospace;
  font-size: 0.75rem;
  background: var(--bg-primary);
  padding: 2px 6px;
  border-radius: 4px;
}

.tool-content {
  margin-bottom: 20px;
  padding: 16px;
  background: var(--bg-tertiary);
  border-radius: 8px;
}

.tool-content.success {
  border-left: 4px solid var(--accent-green);
}

.tool-content.failure {
  border-left: 4px solid #f87171;
}

.tool-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-description {
  font-size: 0.9rem;
  color: var(--text-primary);
  font-style: italic;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: 0.75rem;
  color: var(--text-secondary);
  font-weight: 500;
  text-transform: uppercase;
}

.detail-text {
  font-size: 0.9rem;
  color: var(--text-primary);
  line-height: 1.5;
}

.detail-meta {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.detail-code {
  padding: 12px;
  background: var(--bg-primary);
  border-radius: 6px;
  font-size: 0.8rem;
  font-family: 'SF Mono', Monaco, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
  color: var(--text-primary);
  line-height: 1.5;
}

.detail-output {
  padding: 12px;
  background: var(--bg-primary);
  border-radius: 6px;
  font-size: 0.8rem;
  font-family: 'SF Mono', Monaco, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
  color: var(--text-primary);
  line-height: 1.5;
}

.diff-old {
  border-left: 4px solid #f87171;
  background: rgba(248, 113, 113, 0.1);
}

.diff-new {
  border-left: 4px solid var(--accent-green);
  background: rgba(74, 222, 128, 0.1);
}

.file-path-full {
  display: block;
  font-family: monospace;
  font-size: 0.85rem;
  color: var(--accent-blue);
  background: var(--bg-primary);
  padding: 8px 12px;
  border-radius: 4px;
  word-break: break-all;
}

.pattern-code {
  display: block;
  font-family: monospace;
  font-size: 0.85rem;
  color: var(--accent-yellow);
  background: var(--bg-primary);
  padding: 8px 12px;
  border-radius: 4px;
}

.files-section {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.files-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.file-path {
  font-family: monospace;
  font-size: 0.8rem;
  color: var(--accent-blue);
  background: var(--bg-primary);
  padding: 6px 10px;
  border-radius: 4px;
  word-break: break-all;
}

.raw-section {
  border-top: 1px solid var(--border-color);
  padding-top: 16px;
}

.raw-section summary {
  font-size: 0.8rem;
  color: var(--text-muted);
  cursor: pointer;
  padding: 8px 0;
}

.raw-section summary:hover {
  color: var(--text-secondary);
}

.raw-json {
  margin-top: 8px;
  padding: 12px;
  background: var(--bg-primary);
  border-radius: 6px;
  font-size: 0.7rem;
  font-family: monospace;
  overflow-x: auto;
  max-height: 300px;
  overflow-y: auto;
}

.result-error-badge {
  display: inline-block;
  background: rgba(248, 113, 113, 0.2);
  color: #f87171;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  margin-bottom: 8px;
}

.error-output {
  border-left: 4px solid #f87171;
  background: rgba(248, 113, 113, 0.1);
}

.empty-result {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  background: var(--bg-primary);
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.empty-icon {
  font-size: 1.2rem;
}
</style>
