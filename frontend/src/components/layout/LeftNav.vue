<template>
  <aside class="left-nav" :class="{ collapsed: layout.navCollapsed }">
    <button type="button" class="nav-toggle" @click="layout.toggleNav()" aria-label="Toggle navigation">
      <span class="nav-toggle-icon">{{ layout.navCollapsed ? '→' : '←' }}</span>
    </button>
    <nav class="nav-list">
      <span class="nav-section">MAIN</span>
      <router-link to="/" class="nav-item" active-class="active">Dashboard</router-link>
      <router-link to="/inventory-projection" class="nav-item" active-class="active">Inventory Projection</router-link>
      <router-link to="/planning-grid" class="nav-item" active-class="active">Weekly Planning Grid</router-link>
      <router-link to="/planned-orders" class="nav-item" active-class="active">Planned Orders</router-link>
      <span class="nav-section">DATA</span>
      <router-link to="/admin" class="nav-item" active-class="active">Admin</router-link>
      <router-link to="/imports" class="nav-item" active-class="active">Imports</router-link>
      <router-link to="/exports" class="nav-item" active-class="active">Exports</router-link>
    </nav>
  </aside>
</template>

<script setup lang="ts">
import { useLayoutStore } from '@/stores/layout'

const layout = useLayoutStore()
</script>

<style scoped>
.left-nav {
  width: var(--left-nav-expanded);
  min-width: var(--left-nav-expanded);
  height: 100vh;
  background: var(--nav-bg);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
}
.left-nav.collapsed {
  width: var(--left-nav-collapsed);
  min-width: var(--left-nav-collapsed);
}
.nav-toggle {
  height: 44px;
  min-height: 44px;
  border: none;
  border-bottom: 1px solid var(--border);
  background: transparent;
  color: var(--text);
  cursor: pointer;
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}
.nav-toggle:hover {
  background: var(--hover);
}
.nav-toggle-icon {
  display: block;
}
.nav-list {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0.5rem 0;
}
.nav-section {
  display: block;
  padding: 0.5rem 1rem 0.25rem;
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: 0.05em;
  color: var(--muted);
  text-transform: uppercase;
}
.collapsed .nav-section {
  padding-left: 0.5rem;
  font-size: 0.625rem;
}
.nav-item {
  display: flex;
  align-items: center;
  padding: 0.5rem 1rem;
  color: var(--text);
  text-decoration: none;
  font-size: 0.875rem;
  border-left: 3px solid transparent;
  min-height: 36px;
}
.collapsed .nav-item {
  padding-left: 0.5rem;
  justify-content: center;
}
.nav-item:hover {
  background: var(--hover);
}
.nav-item.active {
  border-left-color: var(--accent);
  background: transparent;
}
.nav-item.active:hover {
  background: var(--hover);
}
</style>
