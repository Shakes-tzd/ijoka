<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import KanbanBoard from './components/KanbanBoard.vue'
import ActivityTimeline from './components/ActivityTimeline.vue'
import StatsBar from './components/StatsBar.vue'
import FeatureDetailModal from './components/FeatureDetailModal.vue'
import ActivityDetailModal from './components/ActivityDetailModal.vue'

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
const loading = ref(true)
const selectedFeature = ref<Feature | null>(null)
const selectedEvent = ref<AgentEvent | null>(null)
const sidebarCollapsed = ref(false)

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
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
})
</script>

<template>
  <div class="app">
    <header>
      <div class="header-left">
        <h1>🎯 AgentKanban</h1>
        <div class="project-selector">
          <select
            :value="selectedProject || ''"
            @change="selectProject(($event.target as HTMLSelectElement).value || null)"
          >
            <option value="">All Projects</option>
            <option
              v-for="project in projects"
              :key="project"
              :value="project"
            >
              {{ getProjectName(project) }}
            </option>
          </select>
        </div>
      </div>
      <StatsBar :stats="stats" />
    </header>

    <main v-if="!loading" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
      <div class="board-container">
        <KanbanBoard
          :todo="todoFeatures"
          :in-progress="inProgressFeatures"
          :done="doneFeatures"
          @feature-click="openFeatureDetail"
        />
      </div>
      <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
        <button class="sidebar-toggle" @click="toggleSidebar" :title="sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'">
          {{ sidebarCollapsed ? '◀' : '▶' }}
        </button>
        <div class="sidebar-content" v-show="!sidebarCollapsed">
          <ActivityTimeline :events="events" @event-click="openEventDetail" />
        </div>
        <div class="collapsed-label" v-show="sidebarCollapsed">
          <span>Activity</span>
        </div>
      </aside>
    </main>

    <div v-else class="loading">
      <p>Loading...</p>
    </div>

    <FeatureDetailModal
      :feature="selectedFeature"
      @close="closeFeatureDetail"
    />

    <ActivityDetailModal
      :event="selectedEvent"
      @close="closeEventDetail"
    />
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
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 20px;
}

.header-left h1 {
  font-size: 1.25rem;
  font-weight: 600;
}

.project-selector select {
  background: var(--bg-tertiary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 0.875rem;
  cursor: pointer;
  min-width: 180px;
}

.project-selector select:hover {
  border-color: var(--accent-blue);
}

.project-selector select:focus {
  outline: none;
  border-color: var(--accent-blue);
  box-shadow: 0 0 0 2px rgba(96, 165, 250, 0.2);
}

main {
  display: grid;
  grid-template-columns: 1fr 320px;
  flex: 1;
  overflow: hidden;
  transition: grid-template-columns 0.3s ease;
}

main.sidebar-collapsed {
  grid-template-columns: 1fr 40px;
}

.board-container {
  padding: 20px;
  overflow-x: auto;
}

.sidebar {
  background: var(--bg-secondary);
  border-left: 1px solid var(--border-color);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 65px);
  position: relative;
  transition: width 0.3s ease;
}

.sidebar.collapsed {
  width: 40px;
}

.sidebar-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.sidebar-toggle {
  position: absolute;
  top: 12px;
  left: -12px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  z-index: 10;
  transition: all 0.2s;
}

.sidebar-toggle:hover {
  background: var(--accent-blue);
  color: white;
  border-color: var(--accent-blue);
}

.collapsed-label {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  font-size: 0.75rem;
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
</style>
