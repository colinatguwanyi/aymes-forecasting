<template>
  <header class="top-bar">
    <h1 class="top-bar-title">{{ title }}</h1>
    <div class="top-bar-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useLayoutStore } from '@/stores/layout'

const route = useRoute()
const layout = useLayoutStore()

const title = computed(() => layout.pageTitle || (route.meta?.title as string) || route.name || 'Supply Planning')
</script>

<style scoped>
.top-bar {
  height: var(--top-bar-height);
  min-height: var(--top-bar-height);
  padding: 0 1rem;
  background: var(--main-bg);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.top-bar-title {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 500;
  color: var(--text);
}
.top-bar-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
</style>
