<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import KanbanBoard from './components/KanbanBoard.vue'
import ActivityTimeline from './components/ActivityTimeline.vue'
import FeatureDetailModal from './components/FeatureDetailModal.vue'
import ActivityDetailModal from './components/ActivityDetailModal.vue'
import ToolIcon from './components/icons/ToolIcon.vue'

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
  createdAt: string
}

interface Stats {
  total: number
  completed: number
  inProgress: number
  percentage: number
  activeSessions: number
}

interface Config {
  watchedProjects: string[]
  syncServerPort: number
  notificationsEnabled: boolean
  selectedProject: string | null
}

const features = ref<Feature[]>([])
const events = ref<AgentEvent[]>([])
const stats = ref<Stats>({ total: 0, completed: 0, inProgress: 0, percentage: 0, activeSessions: 0 })
const projects = ref<string[]>([])
const selectedProject = ref<string | null>(null)
const openProjects = ref<string[]>([]) // Projects open as tabs
const loading = ref(true)
const selectedFeature = ref<Feature | null>(null)
const selectedEvent = ref<AgentEvent | null>(null)
const showSettings = ref(false)
const sidebarCollapsed = ref(false)
const leftPanelCollapsed = ref(false)
const sidebarWidth = ref(320)
const isResizing = ref(false)
const activeView = ref<'board' | 'activity'>('board')
let pollInterval: ReturnType<typeof setInterval> | null = null

// Sidebar resize handling
const MIN_SIDEBAR_WIDTH = 240
const MAX_SIDEBAR_WIDTH = 500

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}

function startResize(_e: MouseEvent) {
  isResizing.value = true
  document.addEventListener('mousemove', handleResize)
  document.addEventListener('mouseup', stopResize)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
}

function handleResize(e: MouseEvent) {
  if (!isResizing.value) return
  const newWidth = window.innerWidth - e.clientX - 48 // 48px for activity bar
  sidebarWidth.value = Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, newWidth))
}

function stopResize() {
  isResizing.value = false
  document.removeEventListener('mousemove', handleResize)
  document.removeEventListener('mouseup', stopResize)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

function openFeatureDetail(feature: Feature) {
  selectedFeature.value = feature
}

function closeFeatureDetail() {
  selectedFeature.value = null
}

function openEventDetail(event: AgentEvent) {
  selectedEvent.value = event
}

function closeEventDetail() {
  selectedEvent.value = null
}

function toggleLeftPanel() {
  leftPanelCollapsed.value = !leftPanelCollapsed.value
}

function openProjectTab(projectDir: string) {
  // Add to open tabs if not already there
  if (!openProjects.value.includes(projectDir)) {
    openProjects.value.push(projectDir)
  }
  // Select this project (also saves to config)
  selectProject(projectDir)
}

function closeProjectTab(projectDir: string, event: Event) {
  event.stopPropagation() // Don't trigger tab selection
  const index = openProjects.value.indexOf(projectDir)
  if (index > -1) {
    openProjects.value.splice(index, 1)
    // If we closed the selected project, select another or null
    if (selectedProject.value === projectDir) {
      if (openProjects.value.length > 0) {
        // Select the previous tab, or the first one
        selectProject(openProjects.value[Math.max(0, index - 1)])
      } else {
        selectProject(null)
      }
    }
  }
}

const todoFeatures = computed(() =>
  features.value.filter(f => !f.passes && !f.inProgress)
)
const inProgressFeatures = computed(() =>
  features.value.filter(f => f.inProgress && !f.passes)
)
const doneFeatures = computed(() =>
  features.value.filter(f => f.passes)
)

async function loadData() {
  try {
    loading.value = true
    const [featuresData, eventsData, statsData, projectsData] = await Promise.all([
      invoke<Feature[]>('get_features', { projectDir: selectedProject.value }),
      invoke<AgentEvent[]>('get_events', { limit: 50 }),
      invoke<Stats>('get_stats'),
      invoke<string[]>('get_projects'),
    ])
    features.value = featuresData
    events.value = eventsData
    stats.value = statsData
    projects.value = projectsData
  } catch (e) {
    console.error('Failed to load data:', e)
  } finally {
    loading.value = false
  }
}

async function selectProject(projectDir: string | null) {
  selectedProject.value = projectDir
  // Save to config
  try {
    const config = await invoke<Config>('get_config')
    config.selectedProject = projectDir
    await invoke('save_config', { config })
  } catch (e) {
    console.error('Failed to save selected project:', e)
  }
  await loadData()
}

function getProjectName(projectDir: string): string {
  // Extract just the folder name from the full path
  const parts = projectDir.split('/')
  return parts[parts.length - 1] || projectDir
}

async function scanProjects() {
  try {
    const projects = await invoke<string[]>('scan_projects')
    console.log('Found projects:', projects)
    // Could show a modal to select projects to watch
  } catch (e) {
    console.error('Failed to scan projects:', e)
  }
}

onMounted(async () => {
  // Load saved project selection
  try {
    const config = await invoke<Config>('get_config')
    if (config.selectedProject) {
      selectedProject.value = config.selectedProject
      // Also add to open tabs
      if (!openProjects.value.includes(config.selectedProject)) {
        openProjects.value.push(config.selectedProject)
      }
    }
  } catch (e) {
    console.error('Failed to load config:', e)
  }

  await loadData()

  // Listen for real-time updates
  await listen<AgentEvent>('agent-event', (event) => {
    events.value = [event.payload, ...events.value.slice(0, 99)]
    // Reload stats when we get a feature completion
    if (event.payload.eventType === 'FeatureCompleted') {
      loadData()
    }
  })

  await listen('features-updated', async () => {
    await loadData()
  })

  await listen('scan-requested', async () => {
    await scanProjects()
  })

  // Poll for new events every 2 seconds (hooks write directly to SQLite)
  pollInterval = setInterval(async () => {
    try {
      const [eventsData, statsData] = await Promise.all([
        invoke<AgentEvent[]>('get_events', { limit: 50 }),
        invoke<Stats>('get_stats'),
      ])
      // Only update if there are new events (compare by first event id)
      if (eventsData.length > 0 && (events.value.length === 0 || eventsData[0].id !== events.value[0]?.id)) {
        events.value = eventsData
        stats.value = statsData
      }
    } catch (e) {
      console.error('Polling error:', e)
    }
  }, 2000)
})

onUnmounted(() => {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
})
</script>

<template>
  <div class="app" :class="{ resizing: isResizing }">
    <!-- Left Activity Bar (VS Code style) -->
    <nav class="activity-bar">
      <div class="activity-bar-top">
        <div class="logo" title="Ijoka">
          <ToolIcon name="target" :size="24" />
        </div>
        <!-- Toggle Left Panel -->
        <button
          class="nav-item"
          :class="{ active: !leftPanelCollapsed }"
          @click="toggleLeftPanel"
          title="Toggle Projects Panel"
        >
          <ToolIcon name="folder" :size="22" />
        </button>
        <!-- View Selector (always visible when project selected) -->
        <template v-if="selectedProject">
          <div class="nav-divider"></div>
          <button
            class="nav-item"
            :class="{ active: activeView === 'board' }"
            @click="activeView = 'board'"
            title="Kanban Board"
          >
            <ToolIcon name="layout" :size="22" />
          </button>
          <button
            class="nav-item"
            :class="{ active: activeView === 'activity' }"
            @click="activeView = 'activity'"
            title="Activity Feed"
          >
            <ToolIcon name="activity" :size="22" />
            <span v-if="stats.activeSessions > 0" class="activity-badge">{{ stats.activeSessions }}</span>
          </button>
        </template>
      </div>
      <div class="activity-bar-bottom">
        <button
          class="nav-item"
          :class="{ active: showSettings }"
          @click="showSettings = true"
          title="Settings"
        >
          <ToolIcon name="settings" :size="22" />
        </button>
      </div>
    </nav>

    <!-- Left Projects Panel -->
    <aside class="projects-panel" :class="{ collapsed: leftPanelCollapsed }">
      <div class="projects-header">
        <span class="projects-title">Projects</span>
      </div>
      <div class="projects-list">
        <button
          v-for="project in projects"
          :key="project"
          class="project-item"
          :class="{ active: selectedProject === project }"
          @click="openProjectTab(project)"
        >
          <span>{{ getProjectName(project) }}</span>
        </button>
      </div>
    </aside>

    <!-- Main Content Area -->
    <div class="main-wrapper">
      <!-- Project Tabs (show when projects are open) -->
      <div class="project-tabs" v-if="openProjects.length > 0">
        <div
          v-for="project in openProjects"
          :key="project"
          class="tab"
          :class="{ active: selectedProject === project }"
          @click="selectProject(project)"
          role="tab"
          tabindex="0"
          @keydown.enter="selectProject(project)"
        >
          <span>{{ getProjectName(project) }}</span>
          <button class="tab-close" @click.stop="closeProjectTab(project, $event)" title="Close">
            <ToolIcon name="x-circle" :size="12" />
          </button>
        </div>
      </div>

      <!-- Main Content -->
      <main v-if="!loading">
        <!-- No Project Selected State -->
        <div v-if="!selectedProject" class="empty-state">
          <ToolIcon name="folder" :size="48" />
          <h2>Select a Project</h2>
          <p>Choose a project from the sidebar to view its kanban board</p>
        </div>
        <!-- Kanban Board View -->
        <div v-else-if="activeView === 'board'" class="board-container">
          <KanbanBoard
            :todo="todoFeatures"
            :in-progress="inProgressFeatures"
            :done="doneFeatures"
            @feature-click="openFeatureDetail"
            @feature-updated="loadData"
          />
        </div>
        <!-- Activity View (full width when selected) -->
        <div v-else-if="activeView === 'activity'" class="activity-view">
          <ActivityTimeline :events="events" @event-click="openEventDetail" />
        </div>
      </main>

      <div v-else class="loading">
        <p>Loading...</p>
      </div>
    </div>

    <!-- Right Activity Sidebar (Resizable) - only show in board view -->
    <aside
      v-if="selectedProject && activeView === 'board'"
      class="sidebar"
      :class="{ collapsed: sidebarCollapsed }"
      :style="{ width: sidebarCollapsed ? '40px' : `${sidebarWidth}px` }"
    >
      <!-- Resize Handle -->
      <div
        class="resize-handle"
        v-show="!sidebarCollapsed"
        @mousedown="startResize"
        title="Drag to resize"
      >
        <div class="resize-grip">
          <ToolIcon name="grip-vertical" :size="12" />
        </div>
      </div>

      <!-- Collapse Toggle -->
      <button
        class="sidebar-toggle"
        @click="toggleSidebar"
        :title="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
      >
        <ToolIcon :name="sidebarCollapsed ? 'panel-left' : 'panel-right'" :size="14" />
      </button>

      <!-- Sidebar Content -->
      <div class="sidebar-content" v-show="!sidebarCollapsed">
        <ActivityTimeline :events="events" @event-click="openEventDetail" />
      </div>

      <!-- Collapsed State -->
      <div class="collapsed-label" v-show="sidebarCollapsed">
        <ToolIcon name="activity" :size="16" />
        <span>Activity</span>
      </div>
    </aside>

    <!-- Modals -->
    <FeatureDetailModal
      :feature="selectedFeature"
      @close="closeFeatureDetail"
    />

    <ActivityDetailModal
      :event="selectedEvent"
      @close="closeEventDetail"
    />

    <!-- Settings Modal -->
    <div v-if="showSettings" class="modal-overlay" @click.self="showSettings = false">
      <div class="settings-modal">
        <div class="modal-header">
          <h2>Settings</h2>
          <button class="modal-close" @click="showSettings = false">
            <ToolIcon name="x-circle" :size="20" />
          </button>
        </div>
        <div class="modal-content">
          <div class="settings-section">
            <h3>Watched Projects</h3>
            <p class="settings-description">Projects being monitored for changes</p>
            <div class="settings-list">
              <div v-for="project in projects" :key="project" class="settings-item">
                <ToolIcon name="folder" :size="14" />
                <span>{{ getProjectName(project) }}</span>
              </div>
              <p v-if="projects.length === 0" class="empty-message">No projects configured</p>
            </div>
          </div>
          <div class="settings-section">
            <h3>About</h3>
            <p class="settings-description">Ijoka v0.1.0</p>
            <p class="settings-description">Unified observability and orchestration for AI coding agents</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style>
:root {
  --bg-primary: #1a1a2e;
  --bg-secondary: #252542;
  --bg-tertiary: #16213e;
  --text-primary: #eee;
  --text-secondary: #888;
  --text-muted: #666;
  --accent-green: #4ade80;
  --accent-yellow: #fbbf24;
  --accent-blue: #60a5fa;
  --accent-purple: #a78bfa;
  --accent-red: #f87171;
  --border-color: #333;
  --card-bg: #2a2a4a;
  --card-hover: #3a3a5a;
  --activity-bar-width: 48px;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.app {
  height: 100vh;
  display: flex;
  flex-direction: row;
  overflow: hidden;
}

.app.resizing {
  cursor: col-resize;
  user-select: none;
}

/* Left Activity Bar (VS Code style) */
.activity-bar {
  width: var(--activity-bar-width);
  background: var(--bg-tertiary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  flex-shrink: 0;
}

.activity-bar-top,
.activity-bar-bottom {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.activity-bar-top {
  padding-top: 8px;
}

.activity-bar-bottom {
  padding-bottom: 12px;
}

.nav-divider {
  width: 24px;
  height: 1px;
  background: var(--border-color);
  margin: 8px 0;
}

.logo {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-blue);
  margin-bottom: 8px;
}

.nav-item {
  position: relative;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.nav-item:hover {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.05);
}

.nav-item.active {
  color: var(--text-primary);
  background: rgba(96, 165, 250, 0.15);
}

.nav-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: var(--accent-blue);
  border-radius: 0 2px 2px 0;
}

.activity-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font-size: 10px;
  font-weight: 600;
  background: var(--accent-blue);
  color: white;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Left Projects Panel */
.projects-panel {
  width: 180px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.2s ease, opacity 0.2s ease;
}

.projects-panel.collapsed {
  width: 0;
  overflow: hidden;
  border-right: none;
}

.projects-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
}

.projects-title {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.projects-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.project-item {
  display: flex;
  align-items: center;
  width: 100%;
  padding: 8px 16px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 0.85rem;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
}

.project-item:hover {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
}

.project-item.active {
  background: rgba(96, 165, 250, 0.15);
  color: var(--text-primary);
}

.project-item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Main wrapper */
.main-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

/* Project Tabs - sticky at top */
.project-tabs {
  display: flex;
  align-items: center;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border-color);
  padding: 0 8px;
  gap: 2px;
  flex-shrink: 0;
  overflow-x: auto;
  position: sticky;
  top: 0;
  z-index: 10;
}

.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  font-size: 0.8rem;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}

.tab:hover {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.03);
}

.tab.active {
  color: var(--text-primary);
  border-bottom-color: var(--accent-blue);
  background: rgba(96, 165, 250, 0.08);
}

.tab-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  margin-left: 4px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0;
  transition: all 0.15s;
}

.tab:hover .tab-close {
  opacity: 1;
}

.tab-close:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-primary);
}

main {
  flex: 1;
  overflow: auto;
  display: flex;
}

/* Empty State */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--text-muted);
  text-align: center;
  padding: 40px;
}

.empty-state h2 {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0;
}

.empty-state p {
  font-size: 0.9rem;
  margin: 0;
}

/* Activity View (full width) */
.activity-view {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
}

.board-container {
  flex: 1;
  padding: 16px;
  overflow: auto;
  min-height: 0; /* Enable flex shrinking */
}

/* Right Sidebar */
.sidebar {
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-color);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
  flex-shrink: 0;
  height: 100%;
  max-height: 100vh;
}

.sidebar.collapsed {
  width: 40px !important;
}

/* Resize Handle */
.resize-handle {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 6px;
  cursor: col-resize;
  background: transparent;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
}

.resize-handle:hover,
.app.resizing .resize-handle {
  background: var(--accent-blue);
}

.resize-grip {
  opacity: 0;
  color: white;
  transition: opacity 0.15s;
}

.resize-handle:hover .resize-grip,
.app.resizing .resize-grip {
  opacity: 1;
}

/* Sidebar Toggle Button */
.sidebar-toggle {
  position: absolute;
  top: 8px;
  left: 8px;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 15;
  transition: all 0.15s;
}

.sidebar-toggle:hover {
  background: var(--accent-blue);
  color: white;
  border-color: var(--accent-blue);
}

.sidebar.collapsed .sidebar-toggle {
  left: 6px;
  top: 6px;
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  margin-left: 6px; /* Account for resize handle */
  min-height: 0; /* Enable flex shrinking for scroll */
}

.collapsed-label {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 100%;
  padding-top: 40px;
  color: var(--text-muted);
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--text-secondary);
}

/* Scrollbar styling */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--bg-primary);
}

::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #444;
}

/* Settings Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.settings-modal {
  background: var(--bg-secondary);
  border-radius: 12px;
  border: 1px solid var(--border-color);
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
}

.modal-header h2 {
  font-size: 1.1rem;
  font-weight: 600;
  margin: 0;
}

.modal-close {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.15s;
}

.modal-close:hover {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.1);
}

.modal-content {
  padding: 20px;
  overflow-y: auto;
}

.settings-section {
  margin-bottom: 24px;
}

.settings-section:last-child {
  margin-bottom: 0;
}

.settings-section h3 {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}

.settings-description {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin: 0 0 12px 0;
}

.settings-list {
  background: var(--bg-tertiary);
  border-radius: 8px;
  padding: 8px;
}

.settings-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.empty-message {
  color: var(--text-muted);
  font-size: 0.8rem;
  text-align: center;
  padding: 12px;
  margin: 0;
}
</style>
