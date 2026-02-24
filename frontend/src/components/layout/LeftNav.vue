<template>
  <aside class="left-nav" :class="{ collapsed: layout.navCollapsed }">
    <button type="button" class="nav-toggle" @click="layout.toggleNav()" aria-label="Toggle navigation">
      <span class="nav-toggle-icon">{{ layout.navCollapsed ? '→' : '←' }}</span>
    </button>
    <nav class="nav-list">
      <span class="nav-section">PLANNING</span>
      <router-link to="/" class="nav-item" active-class="active">Dashboard</router-link>
      <router-link to="/stock-position" class="nav-item" active-class="active">Stock Position</router-link>
      <router-link to="/inventory-projection" class="nav-item" active-class="active">Inventory Projection</router-link>
      <router-link to="/planning-grid" class="nav-item" active-class="active">Weekly Planning Grid</router-link>
      <router-link to="/planned-orders" class="nav-item" active-class="active">Planned Orders</router-link>
      <router-link to="/exceptions" class="nav-item" active-class="active">Exceptions</router-link>

      <span class="nav-section">DATA & SETUP</span>
      <router-link to="/imports" class="nav-item" active-class="active">Imports</router-link>
      <router-link to="/admin/products" class="nav-item" active-class="active">Products</router-link>
      <router-link to="/admin/suppliers" class="nav-item" active-class="active">Suppliers</router-link>
      <router-link to="/admin/warehouses" class="nav-item" active-class="active">Warehouses</router-link>
      <router-link to="/admin/policies" class="nav-item" active-class="active">Policies</router-link>

      <span class="nav-section">OUTPUT</span>
      <router-link to="/reports" class="nav-item" active-class="active">Reports</router-link>
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
  background: white;
  border-right: 1px solid rgb(226 232 240);
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
  height: 2.75rem;
  min-height: 2.75rem;
  border: none;
  border-bottom: 1px solid rgb(226 232 240);
  background: transparent;
  color: rgb(71 85 105);
  cursor: pointer;
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
}
.nav-toggle:hover {
  background: rgb(248 250 252);
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
  font-weight: 600;
  letter-spacing: 0.05em;
  color: rgb(100 116 139);
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
  color: rgb(51 65 85);
  text-decoration: none;
  font-size: 0.875rem;
  border-left: 3px solid transparent;
  min-height: 2rem;
}
.collapsed .nav-item {
  padding-left: 0.5rem;
  justify-content: center;
}
.nav-item:hover {
  background: rgb(248 250 252);
}
.nav-item.active {
  border-left-color: #2563eb;
  background: rgb(239 246 255);
  color: #1d4ed8;
}
.nav-item.active:hover {
  background: rgb(224 242 254);
}
</style>
