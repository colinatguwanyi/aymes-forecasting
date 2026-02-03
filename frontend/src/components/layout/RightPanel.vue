<template>
  <aside v-show="layout.rightPanelOpen" class="right-panel">
    <div class="right-panel-header">
      <span class="right-panel-title">{{ layout.rightPanelTitle }}</span>
      <button type="button" class="right-panel-close" @click="layout.closeRightPanel()" aria-label="Close panel">
        ×
      </button>
    </div>
    <div id="right-panel-body" class="right-panel-body">
      <slot />
    </div>
  </aside>
</template>

<script setup lang="ts">
import { useLayoutStore } from '@/stores/layout'

const layout = useLayoutStore()
</script>

<style scoped>
.right-panel {
  width: var(--right-panel-width);
  min-width: var(--right-panel-width);
  height: 100vh;
  background: var(--main-bg);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
}
.right-panel-header {
  height: 48px;
  min-height: 48px;
  padding: 0 1rem;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.right-panel-title {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text);
}
.right-panel-close {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--muted);
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
  padding: 0;
}
.right-panel-close:hover {
  color: var(--text);
}
.right-panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  font-size: 0.875rem;
}
</style>
