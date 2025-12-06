<script setup lang="ts">
import { computed } from 'vue'
import KanbanColumn from './KanbanColumn.vue'

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

const props = defineProps<{
  todo: Feature[]
  inProgress: Feature[]
  done: Feature[]
}>()

const emit = defineEmits<{
  'feature-click': [feature: Feature]
}>()

const columns = computed(() => [
  { id: 'todo', title: '📋 To Do', features: props.todo, color: 'var(--accent-blue)' },
  { id: 'inProgress', title: '🔄 In Progress', features: props.inProgress, color: 'var(--accent-yellow)' },
  { id: 'done', title: '✅ Done', features: props.done, color: 'var(--accent-green)' },
])
</script>

<template>
  <div class="kanban-board">
    <KanbanColumn
      v-for="column in columns"
      :key="column.id"
      :title="column.title"
      :features="column.features"
      :color="column.color"
      @feature-click="(f) => emit('feature-click', f)"
    />
  </div>
</template>

<style scoped>
.kanban-board {
  display: grid;
  grid-template-columns: repeat(3, minmax(280px, 1fr));
  gap: 16px;
  height: 100%;
  min-height: 0;
}
</style>
