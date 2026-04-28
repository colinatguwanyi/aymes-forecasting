<template>
  <div class="main-column">
    <TopBar />
    <BannerBar />
    <div class="page-content">
      <router-view v-slot="{ Component }">
        <component :is="Component" />
      </router-view>
    </div>
  </div>
</template>

<script setup lang="ts">
import TopBar from './TopBar.vue'
import BannerBar from './BannerBar.vue'
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
  width: 100%;
  max-width: 1600px;
  margin: 0 auto;
  padding: 1.5rem 24px;
  box-sizing: border-box;
}
</style>
