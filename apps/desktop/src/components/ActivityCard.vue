<script setup lang="ts">
import ToolIcon from './icons/ToolIcon.vue'

interface AgentEvent {
  id: number
  eventType: string
  sourceAgent: string
  sessionId: string
  projectDir: string
  toolName?: string
  payload?: string | object  // Can be string (SQLite) or object (Memgraph)
  featureId?: string
  createdAt: string
}

interface ParsedPayload {
  // Common fields
  inputSummary?: string
  preview?: string
  description?: string
  success?: boolean
  filePaths?: string[]
  messageType?: string

  // Bash
  command?: string
  outputPreview?: string

  // Read/Write/Edit
  filePath?: string
  file_path?: string
  oldString?: string
  newString?: string
  contentPreview?: string
  content?: string
  offset?: number
  limit?: number

  // Grep/Glob
  pattern?: string
  path?: string
  glob?: string
  output_mode?: string

  // Task
  prompt?: string
  taskDescription?: string
  subagentType?: string
  subagent_type?: string

  // WebFetch/WebSearch
  url?: string
  query?: string

  // BashOutput
  bash_id?: string
  shell_id?: string

  // TodoWrite
  todos?: Array<{ content?: string; status?: string }>

  // Events
  reason?: string
  stopReason?: string

  [key: string]: unknown
}

const props = defineProps<{
  event: AgentEvent
  expanded?: boolean
  showFeatureLink?: boolean
}>()

const emit = defineEmits<{
  click: []
}>()

// Tool name to icon mapping
const toolIconNames: Record<string, string> = {
  Bash: 'terminal',
  BashOutput: 'terminal-output',
  Read: 'file',
  Write: 'file-plus',
  Edit: 'file-edit',
  Grep: 'search',
  Glob: 'folder-search',
  Task: 'bot',
  TodoWrite: 'check-square',
  TodoRead: 'list',
  WebFetch: 'globe',
  WebSearch: 'search-globe',
}

// Event type to icon mapping (fallback)
const eventIconNames: Record<string, string> = {
  SessionStart: 'rocket',
  SessionEnd: 'flag',
  ToolCall: 'wrench',
  ToolUse: 'wrench',
  FeatureStarted: 'file-edit',
  FeatureCompleted: 'check-square',
  Error: 'x-circle',
  TranscriptUpdated: 'message',
  UserQuery: 'user',
  AgentStop: 'stop',
  SubagentStop: 'cpu',
}

const agentColors: Record<string, string> = {
  'claude-code': '#60a5fa',
  'codex-cli': '#4ade80',
  'gemini-cli': '#fbbf24',
  'hook': '#a78bfa',
  'file-watch': '#64748b',
  'unknown': '#888',
}

function parsePayload(payload?: string | object): ParsedPayload | null {
  if (!payload) return null
  // Handle both string (from SQLite) and object (from Memgraph via serde_json::Value)
  if (typeof payload === 'object') {
    return payload as ParsedPayload
  }
  try {
    return JSON.parse(payload)
  } catch {
    return null
  }
}

function getIconName(event: AgentEvent): string {
  if (event.toolName && toolIconNames[event.toolName]) {
    return toolIconNames[event.toolName]
  }
  return eventIconNames[event.eventType] || 'wrench'
}

function getAgentColor(agent: string): string {
  return agentColors[agent] || '#888'
}

function formatTime(dateStr: string): string {
  if (!dateStr) return '--:--'
  // Memgraph returns timestamps like "2025-12-09T12:41:19.672765+00:00[Etc/UTC]"
  // Remove the [timezone] suffix that JS Date can't parse
  const cleanedStr = dateStr.replace(/\[.*\]$/, '')
  const date = new Date(cleanedStr)
  if (isNaN(date.getTime())) return '--:--'
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function getDescriptiveTitle(event: AgentEvent): string {
  const payload = parsePayload(event.payload)

  switch (event.eventType) {
    case 'UserQuery': {
      const prompt = payload?.prompt || payload?.preview || ''
      if (prompt) {
        // Clean up and truncate the prompt
        const cleaned = prompt.replace(/\s+/g, ' ').trim()
        return truncate(cleaned, 55)
      }
      return 'User Query'
    }

    case 'SessionStart': {
      const project = event.projectDir ? getFileName(event.projectDir) : ''
      return project ? `Session: ${project}` : 'Session Started'
    }

    case 'SessionEnd': {
      const reason = payload?.reason || payload?.stopReason
      return reason ? `Session Ended (${reason})` : 'Session Ended'
    }

    case 'AgentStop': {
      const reason = payload?.reason || payload?.stopReason || 'completed'
      return `Agent Stopped: ${reason}`
    }

    case 'SubagentStop': {
      const task = payload?.taskDescription || payload?.description
      const agentType = payload?.subagentType || payload?.subagent_type
      if (task) {
        return `Subagent Done: ${truncate(task, 35)}`
      }
      if (agentType) {
        return `Subagent Done: ${agentType}`
      }
      return 'Subagent Completed'
    }

    case 'TranscriptUpdated': {
      const msgType = payload?.messageType || event.toolName
      if (msgType === 'tool_result' || event.toolName === 'ToolResult') {
        // Try to show what tool's result
        if (payload?.inputSummary) {
          return `Result: ${truncate(payload.inputSummary, 40)}`
        }
        return 'Tool Result'
      }
      if (msgType === 'tool_use') {
        return 'Tool Use'
      }
      if (msgType === 'assistant') {
        if (payload?.preview) {
          return `Response: ${truncate(payload.preview, 40)}`
        }
        return 'Assistant Response'
      }
      if (msgType === 'user') {
        if (payload?.preview) {
          return `User: ${truncate(payload.preview, 45)}`
        }
        return 'User Message'
      }
      return msgType || 'Transcript Update'
    }

    case 'ToolCall':
    case 'ToolUse':
      if (event.toolName) {
        return getToolTitle(event.toolName, payload)
      }
      return 'Tool Call'

    case 'FeatureStarted': {
      const desc = payload?.featureDescription || payload?.description
      return desc && typeof desc === 'string' ? `Started: ${truncate(desc, 40)}` : 'Feature Started'
    }

    case 'FeatureCompleted': {
      const desc = payload?.featureDescription || payload?.description
      return desc && typeof desc === 'string' ? `Completed: ${truncate(desc, 38)}` : 'Feature Completed'
    }

    case 'Error': {
      const msg = payload?.preview || payload?.description
      return msg && typeof msg === 'string' ? `Error: ${truncate(msg, 42)}` : 'Error'
    }

    default:
      // For unknown events, try to extract something meaningful
      if (event.toolName) {
        return getToolTitle(event.toolName, payload)
      }
      if (payload?.description && typeof payload.description === 'string') {
        return truncate(payload.description, 50)
      }
      if (payload?.preview && typeof payload.preview === 'string') {
        return truncate(payload.preview, 50)
      }
      return event.eventType
  }
}

function getToolTitle(toolName: string, payload: ParsedPayload | null): string {
  switch (toolName) {
    case 'Bash': {
      const cmd = payload?.command || ''
      if (cmd) {
        // Extract meaningful command preview
        const parts = cmd.trim().split(/\s+/)
        const preview = parts.slice(0, 4).join(' ')
        return `$ ${truncate(preview, 45)}`
      }
      return 'Run Command'
    }

    case 'BashOutput': {
      const shellId = payload?.bash_id || payload?.shell_id
      if (shellId) {
        return `Check Output: ${truncate(shellId, 20)}`
      }
      return 'Check Background Output'
    }

    case 'Read': {
      const file = payload?.filePath || payload?.file_path
      if (file) {
        const fileName = getFileName(file)
        if (payload?.offset !== undefined && payload?.limit) {
          return `Read ${fileName} (lines ${payload.offset}-${payload.offset + payload.limit})`
        }
        return `Read ${fileName}`
      }
      return 'Read File'
    }

    case 'Write': {
      const file = payload?.filePath || payload?.file_path
      if (file) {
        const fileName = getFileName(file)
        // Try to show what kind of content
        const content = payload?.content || payload?.contentPreview || ''
        if (content) {
          const identifier = extractEditIdentifier(content)
          if (identifier) {
            return `Write ${identifier} to ${fileName}`
          }
        }
        return `Write ${fileName}`
      }
      return 'Write File'
    }

    case 'Edit': {
      const file = payload?.filePath || payload?.file_path
      const fileName = file ? getFileName(file) : 'File'
      const oldStr = payload?.oldString
      if (oldStr) {
        const identifier = extractEditIdentifier(oldStr)
        if (identifier) {
          return `Edit ${identifier} in ${fileName}`
        }
      }
      return `Edit ${fileName}`
    }

    case 'Grep': {
      const pattern = payload?.pattern
      if (pattern) {
        const searchPath = payload?.path ? ` in ${getFileName(payload.path)}` : ''
        const mode = payload?.output_mode === 'content' ? '' : ' (files)'
        return `Search: "${truncate(pattern, 25)}"${searchPath}${mode}`
      }
      return 'Search Code'
    }

    case 'Glob': {
      const pattern = payload?.pattern
      if (pattern) {
        const searchPath = payload?.path ? ` in ${getFileName(payload.path)}` : ''
        return `Find: ${truncate(pattern, 30)}${searchPath}`
      }
      return 'Find Files'
    }

    case 'Task': {
      const desc = payload?.description || payload?.taskDescription
      const agentType = payload?.subagentType || payload?.subagent_type
      if (desc) {
        const prefix = agentType ? `[${agentType}] ` : ''
        return `${prefix}${truncate(desc, 40)}`
      }
      if (agentType) {
        return `Task: ${agentType}`
      }
      return 'Run Task'
    }

    case 'TodoWrite': {
      const todos = payload?.todos
      if (todos && Array.isArray(todos)) {
        const inProgress = todos.filter(t => t.status === 'in_progress').length
        const pending = todos.filter(t => t.status === 'pending').length
        const completed = todos.filter(t => t.status === 'completed').length
        return `Todos: ${completed}✓ ${inProgress}⟳ ${pending}○`
      }
      if (payload?.inputSummary) {
        return `Todos: ${truncate(payload.inputSummary, 35)}`
      }
      return 'Update Todos'
    }

    case 'TodoRead':
      return 'Read Todos'

    case 'WebFetch': {
      const url = payload?.url
      if (url) {
        try {
          const urlObj = new URL(url)
          return `Fetch: ${urlObj.hostname}${truncate(urlObj.pathname, 20)}`
        } catch {
          return `Fetch: ${truncate(url, 40)}`
        }
      }
      return 'Fetch Web Page'
    }

    case 'WebSearch': {
      const query = payload?.query
      if (query) {
        return `Search: "${truncate(query, 35)}"`
      }
      return 'Web Search'
    }

    case 'NotebookEdit': {
      const notebook = payload?.filePath || payload?.file_path
      if (notebook) {
        return `Edit Notebook: ${getFileName(notebook)}`
      }
      return 'Edit Notebook'
    }

    case 'AskUser':
    case 'AskUserQuestion':
      return 'Ask User Question'

    case 'ListDir':
    case 'LS': {
      const dir = payload?.path || payload?.filePath
      if (dir) {
        return `List: ${getFileName(dir)}`
      }
      return 'List Directory'
    }

    default:
      return toolName
  }
}

function truncate(str: string, maxLen: number): string {
  if (str.length <= maxLen) return str
  return str.slice(0, maxLen - 1) + '…'
}

function extractEditIdentifier(oldString: string): string | null {
  const trimmed = oldString.trim()

  // CSS selector: .class-name or #id-name
  const cssMatch = trimmed.match(/^([.#][\w-]+)/)
  if (cssMatch) {
    return cssMatch[1]
  }

  // Function definition: function name, const name =, export function
  const funcMatch = trimmed.match(/(?:export\s+)?(?:async\s+)?function\s+(\w+)/)
  if (funcMatch) {
    return `${funcMatch[1]}()`
  }

  // Arrow function or const: const name = or let name =
  const constMatch = trimmed.match(/(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=/)
  if (constMatch) {
    return constMatch[1]
  }

  // Class definition
  const classMatch = trimmed.match(/(?:export\s+)?class\s+(\w+)/)
  if (classMatch) {
    return `class ${classMatch[1]}`
  }

  // Interface or type definition
  const typeMatch = trimmed.match(/(?:export\s+)?(?:interface|type)\s+(\w+)/)
  if (typeMatch) {
    return typeMatch[1]
  }

  // Import statement - show what's being imported
  const importMatch = trimmed.match(/import\s+(?:{([^}]+)}|(\w+))/)
  if (importMatch) {
    const imported = (importMatch[1] || importMatch[2]).trim().split(',')[0].trim()
    return `import ${truncate(imported, 15)}`
  }

  // HTML/Vue element
  const htmlMatch = trimmed.match(/^<(\w+[-\w]*)/)
  if (htmlMatch) {
    return `<${htmlMatch[1]}>`
  }

  // Rust: fn name, pub fn name, impl Name
  const rustFnMatch = trimmed.match(/(?:pub\s+)?fn\s+(\w+)/)
  if (rustFnMatch) {
    return `fn ${rustFnMatch[1]}`
  }

  const rustImplMatch = trimmed.match(/impl(?:<[^>]+>)?\s+(\w+)/)
  if (rustImplMatch) {
    return `impl ${rustImplMatch[1]}`
  }

  // Python: def name
  const pyMatch = trimmed.match(/def\s+(\w+)/)
  if (pyMatch) {
    return `def ${pyMatch[1]}`
  }

  // Fallback: first meaningful word (skip common keywords)
  const words = trimmed.split(/\s+/).filter(w =>
    !['const', 'let', 'var', 'function', 'export', 'import', 'return', 'if', 'else', 'for', 'while'].includes(w)
  )
  if (words[0] && words[0].length > 2 && words[0].length < 30) {
    return truncate(words[0], 20)
  }

  return null
}

function getFileName(path: string): string {
  const parts = path.split('/')
  return parts[parts.length - 1] || path
}

function getEventTypeBadge(eventType: string): string {
  switch (eventType) {
    case 'ToolCall': return 'call'
    case 'TranscriptUpdated': return 'result'
    case 'UserQuery': return 'query'
    case 'SessionStart': return 'start'
    case 'SessionEnd': return 'end'
    case 'AgentStop': return 'stop'
    case 'SubagentStop': return 'agent'
    default: return eventType.toLowerCase()
  }
}

function getSuccessStatus(event: AgentEvent): boolean | null {
  const payload = parsePayload(event.payload)
  if (payload?.success !== undefined) {
    return payload.success as boolean
  }
  return null
}

const successStatus = getSuccessStatus(props.event)
</script>

<template>
  <div
    class="activity-card"
    :class="{
      'status-success': successStatus === true,
      'status-error': successStatus === false,
      'expanded': expanded
    }"
    @click="emit('click')"
  >
    <!-- Left: Icon + Type stacked -->
    <div class="card-left">
      <div class="card-icon">
        <ToolIcon :name="getIconName(event)" :size="18" />
      </div>
      <span class="event-type-label">{{ getEventTypeBadge(event.eventType) }}</span>
    </div>

    <!-- Right: Content -->
    <div class="card-body">
      <!-- Title (prominent) -->
      <p class="card-title">{{ getDescriptiveTitle(event) }}</p>

      <!-- Feature link if present -->
      <span v-if="showFeatureLink && event.featureId" class="feature-link">
        {{ event.featureId.split(':').pop() }}
      </span>

      <!-- Footer: Agent dot + Time + Status -->
      <div class="card-footer">
        <span
          class="agent-dot"
          :style="{ background: getAgentColor(event.sourceAgent) }"
          :title="event.sourceAgent"
        ></span>
        <span class="event-time">{{ formatTime(event.createdAt) }}</span>
        <span v-if="successStatus === true" class="status-check" title="Success">&#10003;</span>
        <span v-if="successStatus === false" class="status-x" title="Failed">&#10007;</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.activity-card {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  background: var(--card-bg);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.activity-card:hover {
  background: var(--card-hover);
}

.activity-card.expanded {
  background: var(--bg-secondary);
}

/* Left column: Icon + Type stacked */
.card-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  width: 40px;
}

.card-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border-radius: 8px;
  color: var(--text-secondary);
}

.activity-card.status-success .card-icon {
  color: var(--accent-green);
  background: rgba(74, 222, 128, 0.1);
}

.activity-card.status-error .card-icon {
  color: #f87171;
  background: rgba(248, 113, 113, 0.1);
}

.event-type-label {
  font-size: 0.55rem;
  color: var(--text-muted);
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.02em;
}

/* Right column: Content */
.card-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.card-title {
  font-size: 0.85rem;
  color: var(--text-primary);
  line-height: 1.3;
  font-weight: 500;
}

.feature-link {
  font-size: 0.65rem;
  color: var(--accent-blue);
  background: rgba(96, 165, 250, 0.1);
  padding: 2px 6px;
  border-radius: 3px;
  align-self: flex-start;
}

/* Footer: Agent dot + Time + Status */
.card-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
}

.agent-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.event-time {
  font-size: 0.7rem;
  color: var(--text-muted);
}

.status-check {
  color: var(--accent-green);
  font-size: 0.8rem;
  font-weight: bold;
  margin-left: auto;
}

.status-x {
  color: var(--accent-red);
  font-size: 0.8rem;
  font-weight: bold;
  margin-left: auto;
}
</style>
