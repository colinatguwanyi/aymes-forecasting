<template>
  <div v-if="banner.items.length" class="banner-bar">
    <div
      v-for="b in banner.items"
      :key="b.id"
      class="banner-item"
      :class="b.type"
    >
      <span class="banner-title">{{ b.title }}</span>
      <span class="banner-message">{{ b.message }}</span>
      <button
        v-if="b.dismissible"
        type="button"
        class="banner-dismiss"
        aria-label="Dismiss"
        @click="banner.dismiss(b.id)"
      >×</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useBannerStore } from '@/stores/banner'

const banner = useBannerStore()
</script>

<style scoped>
.banner-bar {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: rgb(248 250 252);
}
.banner-item {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: 0.375rem;
  font-size: 0.875rem;
}
.banner-item.success {
  background: rgb(220 252 231);
  border: 1px solid rgb(134 239 172);
  color: rgb(22 101 52);
}
.banner-item.error {
  background: rgb(254 226 226);
  border: 1px solid rgb(252 165 165);
  color: rgb(127 29 29);
}
.banner-item.info {
  background: rgb(239 246 255);
  border: 1px solid rgb(191 219 254);
  color: rgb(30 64 175);
}
.banner-title { font-weight: 600; flex-shrink: 0; }
.banner-message { flex: 1; }
.banner-dismiss {
  flex-shrink: 0;
  width: 1.5rem;
  height: 1.5rem;
  padding: 0;
  border: none;
  background: transparent;
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
  opacity: 0.7;
}
.banner-dismiss:hover { opacity: 1; }
</style>
