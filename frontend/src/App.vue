<template>
  <div class="app-root">
    <div v-if="auth.error && !auth.loading" class="auth-banner">
      {{ auth.error }}
    </div>
    <AppShell />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import AppShell from '@/components/layout/AppShell.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

onMounted(() => {
  auth.loadMe()
})
</script>

<style scoped>
.app-root {
  min-height: 100vh;
}
.auth-banner {
  background: rgb(254 226 226);
  color: rgb(153 27 27);
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  text-align: center;
}
</style>
