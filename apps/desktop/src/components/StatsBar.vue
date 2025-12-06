<script setup lang="ts">
import { computed } from 'vue'

interface Stats {
  total: number
  completed: number
  inProgress: number
  percentage: number
  activeSessions: number
}

const props = defineProps<{
  stats: Stats
}>()

const pending = computed(() => 
  props.stats.total - props.stats.completed - props.stats.inProgress
)
</script>

<template>
  <div class="stats-bar">
    <div class="stat done">
      <span class="value">{{ stats.completed }}</span>
      <span class="label">Done</span>
    </div>
    
    <div class="stat in-progress">
      <span class="value">{{ stats.inProgress }}</span>
      <span class="label">In Progress</span>
    </div>
    
    <div class="stat pending">
      <span class="value">{{ pending }}</span>
      <span class="label">To Do</span>
    </div>
    
    <div class="stat percentage">
      <span class="value">{{ Math.round(stats.percentage) }}%</span>
      <span class="label">Complete</span>
    </div>
    
    <div class="stat sessions">
      <span class="value">{{ stats.activeSessions }}</span>
      <span class="label">Active</span>
    </div>
  </div>
</template>

<style scoped>
.stats-bar {
  display: flex;
  gap: 16px;
}

.stat {
  background: var(--bg-tertiary);
  padding: 8px 16px;
  border-radius: 6px;
  text-align: center;
  min-width: 70px;
}

.stat .value {
  font-size: 1.25rem;
  font-weight: 700;
  display: block;
}

.stat .label {
  font-size: 0.65rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat.done .value {
  color: var(--accent-green);
}

.stat.in-progress .value {
  color: var(--accent-yellow);
}

.stat.pending .value {
  color: var(--accent-blue);
}

.stat.percentage .value {
  color: var(--accent-purple);
}

.stat.sessions .value {
  color: var(--text-primary);
}
</style>
