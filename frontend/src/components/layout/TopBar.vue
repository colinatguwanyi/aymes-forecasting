<template>
  <header class="top-bar">
    <div class="top-bar-inner">
      <h1 class="top-bar-title">{{ title }}</h1>
      <div class="top-bar-actions">
        <slot name="actions" />
        <span v-if="auth.authenticated" class="user-badge" :title="auth.roles.join(', ')">
          {{ auth.user?.display_name || auth.user?.email || 'User' }}
          <span v-if="auth.roles.length" class="roles-hint">({{ auth.roles.join(', ') }})</span>
        </span>
        <router-link to="/" class="logo-link" aria-label="Home">
          <img src="@/assets/aymes-logo.svg" alt="AYMES" class="logo-img" />
        </router-link>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useLayoutStore } from '@/stores/layout'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const layout = useLayoutStore()
const auth = useAuthStore()

const title = computed(() => layout.pageTitle || (route.meta?.title as string) || route.name || 'Weekly Supply Planning')
</script>

<style scoped>
.top-bar {
  position: sticky;
  top: 0;
  z-index: 30;
  height: 3.5rem;
  min-height: 3.5rem;
  background: white;
  border-bottom: 1px solid rgb(226 232 240);
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.top-bar-inner {
  width: 100%;
  max-width: 80rem;
  margin: 0 auto;
  padding: 0 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.top-bar-title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text, #1a3c68);
}
.top-bar-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.logo-link {
  display: flex;
  align-items: center;
  text-decoration: none;
}
.logo-img {
  height: 1.75rem;
  width: auto;
}
.user-badge {
  font-size: 0.8125rem;
  color: rgb(71 85 105);
}
.roles-hint {
  font-size: 0.75rem;
  color: rgb(100 116 139);
}
</style>
