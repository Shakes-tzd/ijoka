<script setup lang="ts">
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

defineProps<{
  title: string
  features: Feature[]
  color: string
}>()

const emit = defineEmits<{
  'feature-click': [feature: Feature]
}>()

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
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return `${Math.floor(diff / 86400000)}d ago`
}
</script>

<template>
  <div class="kanban-column">
    <div class="column-header" :style="{ borderColor: color }">
      <span class="column-title">{{ title }}</span>
      <span class="column-count">{{ features.length }}</span>
    </div>
    
    <div class="column-content">
      <div
        v-for="feature in features"
        :key="feature.id"
        class="feature-card"
        @click="emit('feature-click', feature)"
      >
        <div class="card-header">
          <span
            class="category-badge"
            :style="{ backgroundColor: getCategoryColor(feature.category) + '20', color: getCategoryColor(feature.category) }"
          >
            {{ feature.category }}
          </span>
          <span v-if="feature.agent" class="agent-badge">
            🤖 {{ feature.agent }}
          </span>
        </div>
        
        <p class="card-description">{{ feature.description }}</p>
        
        <div class="card-footer">
          <span class="card-time">{{ formatTime(feature.updatedAt) }}</span>
        </div>
      </div>
      
      <div v-if="features.length === 0" class="empty-column">
        <p>No features</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kanban-column {
  display: flex;
  flex-direction: column;
  background: var(--bg-tertiary);
  border-radius: 8px;
  min-height: 0;
  max-height: calc(100vh - 140px);
}

.column-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 2px solid;
  flex-shrink: 0;
}

.column-title {
  font-weight: 600;
  font-size: 0.9rem;
}

.column-count {
  background: var(--bg-secondary);
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.column-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.feature-card {
  background: var(--card-bg);
  border-radius: 6px;
  padding: 12px;
  transition: background 0.2s;
  cursor: pointer;
}

.feature-card:hover {
  background: var(--card-hover);
}

.card-header {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.category-badge {
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 500;
  text-transform: uppercase;
}

.agent-badge {
  font-size: 0.7rem;
  color: var(--text-secondary);
}

.card-description {
  font-size: 0.85rem;
  line-height: 1.4;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.card-footer {
  display: flex;
  justify-content: flex-end;
}

.card-time {
  font-size: 0.7rem;
  color: var(--text-muted);
}

.empty-column {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--text-muted);
  font-size: 0.85rem;
}
</style>
