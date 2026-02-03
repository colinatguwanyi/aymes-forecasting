<template>
  <div class="app-shell">
    <LeftNav />
    <MainColumn />
    <RightPanel />
  </div>
</template>

<script setup lang="ts">
import LeftNav from './LeftNav.vue'
import MainColumn from './MainColumn.vue'
import RightPanel from './RightPanel.vue'
</script>

<style scoped>
.app-shell {
  display: flex;
  width: 100%;
  min-height: 100vh;
  height: 100vh;
}
</style>
