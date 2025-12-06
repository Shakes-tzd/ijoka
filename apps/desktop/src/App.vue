<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import KanbanBoard from './components/KanbanBoard.vue'
import ActivityTimeline from './components/ActivityTimeline.vue'
import StatsBar from './components/StatsBar.vue'
import FeatureDetailModal from './components/FeatureDetailModal.vue'

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

const features = ref<Feature[]>([])
const events = ref<AgentEvent[]>([])
const stats = ref<Stats>({ total: 0, completed: 0, inProgress: 0, percentage: 0, activeSessions: 0 })
const selectedProject = ref<string | null>(null)
const loading = ref(true)
const selectedFeature = ref<Feature | null>(null)

function openFeatureDetail(feature: Feature) {
  selectedFeature.value = feature
}

function closeFeatureDetail() {
  selectedFeature.value = null
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
    const [featuresData, eventsData, statsData] = await Promise.all([
      invoke<Feature[]>('get_features', { projectDir: selectedProject.value }),
      invoke<AgentEvent[]>('get_events', { limit: 50 }),
      invoke<Stats>('get_stats'),
    ])
    features.value = featuresData
    events.value = eventsData
    stats.value = statsData
  } catch (e) {
    console.error('Failed to load data:', e)
  } finally {
    loading.value = false
  }
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
      </div>
      <StatsBar :stats="stats" />
    </header>

    <main v-if="!loading">
      <div class="board-container">
        <KanbanBoard
          :todo="todoFeatures"
          :in-progress="inProgressFeatures"
          :done="doneFeatures"
          @feature-click="openFeatureDetail"
        />
      </div>
      <aside class="sidebar">
        <ActivityTimeline :events="events" />
      </aside>
    </main>

    <div v-else class="loading">
      <p>Loading...</p>
    </div>

    <FeatureDetailModal
      :feature="selectedFeature"
      @close="closeFeatureDetail"
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

.header-left h1 {
  font-size: 1.25rem;
  font-weight: 600;
}

main {
  display: grid;
  grid-template-columns: 1fr 320px;
  flex: 1;
  overflow: hidden;
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
