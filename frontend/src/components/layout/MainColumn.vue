<template>
  <div class="main-column">
    <TopBar />
    <div class="page-content">
      <router-view v-slot="{ Component }">
        <component :is="Component" />
      </router-view>
    </div>
  </div>
</template>

<script setup lang="ts">
import TopBar from './TopBar.vue'
</script>

<style scoped>
.main-column {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}
.page-content {
  flex: 1;
  overflow: auto;
  background: rgb(248 250 252);
  max-width: 80rem;
  margin: 0 auto;
  padding: 1.5rem;
}
</style>
