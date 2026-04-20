<template>
  <aside class="left-nav" :class="{ collapsed: layout.navCollapsed }">
    <button type="button" class="nav-toggle" @click="layout.toggleNav()" aria-label="Toggle navigation">
      <span class="nav-toggle-icon">{{ layout.navCollapsed ? '→' : '←' }}</span>
    </button>
    <nav class="nav-list">

      <span class="nav-section">GETTING STARTED</span>
      <router-link to="/setup" class="nav-item" active-class="active">Setup Checklist</router-link>

      <template v-if="auth.authenticated">
        <span class="nav-section">HOME</span>
        <router-link to="/" class="nav-item" active-class="active">Supply Dashboard</router-link>
      </template>

      <template v-if="auth.canPlanner()">
        <span class="nav-section">SUPPLY PLANNING</span>
        <router-link to="/inventory-projection" class="nav-item" active-class="active">Inventory Projection</router-link>
        <router-link to="/planning-grid" class="nav-item" active-class="active">Weekly Planning Grid</router-link>
        <router-link to="/planned-orders" class="nav-item" active-class="active">Planned Orders</router-link>
        <router-link to="/stock-projection" class="nav-item" active-class="active">Stock Projection</router-link>
        <router-link to="/stock-position" class="nav-item" active-class="active">Stock Position</router-link>
        <router-link to="/exceptions" class="nav-item" active-class="active">Exceptions</router-link>
        <router-link to="/planning/scenario-manager" class="nav-item" active-class="active">Scenario Manager</router-link>
      </template>

      <template v-if="auth.canPlanner()">
        <span class="nav-section">FORECAST</span>
        <router-link to="/forecast/dashboard" class="nav-item" active-class="active">Forecast Dashboard</router-link>
        <router-link to="/forecast/runs" class="nav-item" active-class="active">Run Forecast</router-link>
        <router-link to="/forecast/scenarios" class="nav-item" active-class="active">Scenarios</router-link>
        <router-link to="/forecast/exports" class="nav-item" active-class="active">Forecast Export</router-link>
      </template>

      <span class="nav-section">REPORTS &amp; DATA</span>
      <router-link to="/reports" class="nav-item" active-class="active">Reports hub</router-link>
      <router-link to="/reports/data-health" class="nav-item" active-class="active">Data Health</router-link>
      <router-link to="/reports/stock-coverage" class="nav-item" active-class="active">Stock Coverage</router-link>
      <router-link to="/reports/stock-on-hand-history" class="nav-item" active-class="active">SOH History (SKU)</router-link>
      <router-link to="/reports/sales-grid" class="nav-item" active-class="active">Sales Data</router-link>
      <router-link to="/reports/stock-on-hand-grid" class="nav-item" active-class="active">Stock (SOH) Grid</router-link>

      <template v-if="auth.canPlanner()">
        <span class="nav-section">EXPORTS</span>
        <router-link to="/exports" class="nav-item" active-class="active">Planning Exports</router-link>
      </template>

      <template v-if="auth.canAdmin()">
        <span class="nav-section">ADMIN</span>
        <router-link to="/admin" class="nav-item" active-class="active">Admin console</router-link>
        <span class="nav-section">MASTER DATA</span>
        <router-link to="/admin/products" class="nav-item" active-class="active">Products</router-link>
        <router-link to="/admin/suppliers" class="nav-item" active-class="active">Suppliers</router-link>
        <router-link to="/admin/warehouses" class="nav-item" active-class="active">Warehouses</router-link>
        <router-link to="/admin/lanes" class="nav-item" active-class="active">Lanes</router-link>
        <router-link to="/admin/timelines" class="nav-item" active-class="active">Timelines</router-link>
        <router-link to="/imports" class="nav-item" active-class="active">Imports</router-link>
      </template>

      <template v-if="auth.canAdmin()">
        <span class="nav-section">SETTINGS</span>
        <router-link to="/admin/policies" class="nav-item" active-class="active">Stock Rules</router-link>
        <router-link to="/admin/forecast-methods" class="nav-item" active-class="active">Forecasting Methods</router-link>
        <router-link to="/admin/forecast-engine" class="nav-item" active-class="active">Forecast Settings</router-link>
        <router-link to="/admin/settings" class="nav-item" active-class="active">Admin Settings</router-link>
        <router-link to="/admin/import-formats" class="nav-item" active-class="active">Import Formats</router-link>
        <router-link to="/admin/warehouse-product-codes" class="nav-item" active-class="active">Warehouse Product Codes</router-link>
      </template>

    </nav>
  </aside>
</template>

<script setup lang="ts">
import { useLayoutStore } from '@/stores/layout'
import { useAuthStore } from '@/stores/auth'

const layout = useLayoutStore()
const auth = useAuthStore()
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
