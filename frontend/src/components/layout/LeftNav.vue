<template>
  <aside class="left-nav" :class="{ collapsed: layout.navCollapsed }">
    <button type="button" class="nav-toggle" @click="layout.toggleNav()" aria-label="Toggle navigation">
      <span class="nav-toggle-icon">{{ layout.navCollapsed ? '→' : '←' }}</span>
    </button>
    <button
      v-show="!layout.navCollapsed"
      type="button"
      class="nav-collapse-all"
      :disabled="!anyGroupOpen"
      @click="closeAllGroups"
    >
      Collapse all sections
    </button>
    <nav class="nav-list" aria-label="Main">
      <div class="nav-group">
        <button
          v-show="!layout.navCollapsed"
          type="button"
          class="nav-group-toggle"
          :aria-expanded="open.data"
          @click="toggle('data')"
        >
          <span class="nav-group-label">Data</span>
          <span class="nav-chevron" :class="{ open: open.data }" aria-hidden="true">▼</span>
        </button>
        <div v-show="layout.navCollapsed || open.data" class="nav-group-body">
          <router-link to="/data" class="nav-item" active-class="active">Data hub</router-link>
          <template v-if="auth.canAdmin()">
            <router-link to="/imports" class="nav-item nav-item--sub" active-class="active">Imports</router-link>
            <router-link to="/imports/rejections" class="nav-item nav-item--sub" active-class="active">Import rejections</router-link>
          </template>
          <router-link to="/reports/data-health" class="nav-item nav-item--sub" active-class="active">Data Health</router-link>
          <router-link to="/reports" class="nav-item nav-item--sub" active-class="active">Reports hub</router-link>
          <router-link to="/reports/sales-grid" class="nav-item nav-item--sub" active-class="active">Sales Data</router-link>
          <router-link to="/reports/stock-on-hand-grid" class="nav-item nav-item--sub" active-class="active">Stock (SOH) Grid</router-link>
          <router-link to="/reports/stock-on-hand-history" class="nav-item nav-item--sub" active-class="active">SOH History (SKU)</router-link>
          <router-link to="/reports/stock-coverage" class="nav-item nav-item--sub" active-class="active">Stock Coverage</router-link>
        </div>
      </div>

      <template v-if="auth.canPlanner()">
        <div class="nav-group">
          <button
            v-show="!layout.navCollapsed"
            type="button"
            class="nav-group-toggle"
            :aria-expanded="open.runCenter"
            @click="toggle('runCenter')"
          >
            <span class="nav-group-label">Run Center</span>
            <span class="nav-chevron" :class="{ open: open.runCenter }" aria-hidden="true">▼</span>
          </button>
          <div v-show="layout.navCollapsed || open.runCenter" class="nav-group-body">
            <router-link to="/run-center" class="nav-item" active-class="active">Run Center</router-link>
            <router-link to="/forecast/check" class="nav-item nav-item--sub" active-class="active">Forecast Check</router-link>
            <router-link to="/forecast/runs" class="nav-item nav-item--sub" active-class="active">Run Forecast</router-link>
            <router-link to="/forecast/dashboard" class="nav-item nav-item--sub" active-class="active">Forecast Dashboard</router-link>
            <router-link to="/planning/scenario-manager" class="nav-item nav-item--sub" active-class="active">Scenario Manager</router-link>
            <router-link to="/forecast/scenarios" class="nav-item nav-item--sub" active-class="active">Forecast Scenarios</router-link>
            <router-link to="/forecast/exports" class="nav-item nav-item--sub" active-class="active">Forecast Exports</router-link>
          </div>
        </div>

        <div class="nav-group">
          <button
            v-show="!layout.navCollapsed"
            type="button"
            class="nav-group-toggle"
            :aria-expanded="open.workbench"
            @click="toggle('workbench')"
          >
            <span class="nav-group-label">Planner Workbench</span>
            <span class="nav-chevron" :class="{ open: open.workbench }" aria-hidden="true">▼</span>
          </button>
          <div v-show="layout.navCollapsed || open.workbench" class="nav-group-body">
            <router-link to="/workbench" class="nav-item" active-class="active">Workbench</router-link>
            <router-link to="/" class="nav-item nav-item--sub" exact-active-class="active">Supply Dashboard</router-link>
            <router-link to="/planning-grid" class="nav-item nav-item--sub" active-class="active">Weekly Planning Grid</router-link>
            <router-link to="/exceptions" class="nav-item nav-item--sub" active-class="active">Exceptions</router-link>
            <router-link to="/inventory-projection" class="nav-item nav-item--sub" active-class="active">Inventory Projection</router-link>
            <router-link to="/stock-position" class="nav-item nav-item--sub" active-class="active">Stock Position</router-link>
            <router-link to="/stock-projection" class="nav-item nav-item--sub" active-class="active">Stock Projection</router-link>
            <router-link to="/planned-orders" class="nav-item nav-item--sub" active-class="active">Planned Orders</router-link>
            <router-link to="/sku-detail" class="nav-item nav-item--sub" active-class="active">SKU Detail</router-link>
            <router-link to="/exports" class="nav-item nav-item--sub" active-class="active">Planning Exports</router-link>
          </div>
        </div>
      </template>

      <div class="nav-group">
        <button
          v-show="!layout.navCollapsed"
          type="button"
          class="nav-group-toggle"
          :aria-expanded="open.setup"
          @click="toggle('setup')"
        >
          <span class="nav-group-label">Setup</span>
          <span class="nav-chevron" :class="{ open: open.setup }" aria-hidden="true">▼</span>
        </button>
        <div v-show="layout.navCollapsed || open.setup" class="nav-group-body">
          <router-link to="/setup" class="nav-item" active-class="active">Setup Checklist</router-link>
          <template v-if="auth.canAdmin()">
            <router-link v-slot="{ href, navigate }" to="/admin" custom>
              <a
                :href="href"
                class="nav-item nav-item--sub"
                :class="{ active: isExactAdminHome }"
                @click.prevent="navigate()"
              >Admin home</a>
            </router-link>
            <router-link to="/admin/products" class="nav-item nav-item--sub" active-class="active">Products</router-link>
            <router-link to="/admin/warehouses" class="nav-item nav-item--sub" active-class="active">Locations</router-link>
            <router-link to="/admin/suppliers" class="nav-item nav-item--sub" active-class="active">Suppliers</router-link>
            <router-link to="/admin/lanes" class="nav-item nav-item--sub" active-class="active">Lanes</router-link>
            <router-link to="/admin/timelines" class="nav-item nav-item--sub" active-class="active">Timelines</router-link>
            <router-link to="/admin/policies" class="nav-item nav-item--sub" active-class="active">Stock Rules</router-link>
            <router-link to="/admin/forecast-methods" class="nav-item nav-item--sub" active-class="active">Forecasting Methods</router-link>
            <router-link to="/admin/forecast-engine" class="nav-item nav-item--sub" active-class="active">Forecast Settings</router-link>
            <router-link to="/admin/import-formats" class="nav-item nav-item--sub" active-class="active">Import Formats</router-link>
            <router-link to="/admin/warehouse-product-codes" class="nav-item nav-item--sub" active-class="active">Location Product Codes</router-link>
            <router-link to="/admin/data-management" class="nav-item nav-item--sub" active-class="active">Data Management</router-link>
            <router-link to="/admin/settings" class="nav-item nav-item--sub" active-class="active">Admin Settings</router-link>
          </template>
        </div>
      </div>
    </nav>
  </aside>
</template>

<script setup lang="ts">
import { reactive, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useLayoutStore } from '@/stores/layout'
import { useAuthStore } from '@/stores/auth'

const layout = useLayoutStore()
const auth = useAuthStore()
const route = useRoute()

/** Only highlight Admin home on redirect target, not on every /admin/* tab. */
const isExactAdminHome = computed(() => {
  const p = route.path
  return p === '/admin' || p === '/admin/'
})

const open = reactive({
  data: true,
  runCenter: true,
  workbench: true,
  setup: false,
})

function toggle(key: keyof typeof open) {
  open[key] = !open[key]
}

const anyGroupOpen = computed(
  () => open.data || open.runCenter || open.workbench || open.setup
)

function closeAllGroups(): void {
  open.data = false
  open.runCenter = false
  open.workbench = false
  open.setup = false
}

function syncOpenFromRoute() {
  const p = route.path
  const name = route.name
  if (
    name === 'DataHub' ||
    p.startsWith('/data') ||
    p.startsWith('/imports') ||
    p.startsWith('/reports')
  ) {
    open.data = true
  }
  if (
    name === 'RunCenter' ||
    p.startsWith('/run-center') ||
    p.startsWith('/forecast/') ||
    p.startsWith('/planning/scenario-manager')
  ) {
    open.runCenter = true
  }
  if (
    p === '/' ||
    p === '' ||
    name === 'Dashboard' ||
    name === 'PlannerWorkbench' ||
    p.startsWith('/workbench') ||
    p.startsWith('/inventory-projection') ||
    p.startsWith('/planning-grid') ||
    p.startsWith('/planned-orders') ||
    p.startsWith('/stock-projection') ||
    p.startsWith('/stock-position') ||
    p.startsWith('/exceptions') ||
    p.startsWith('/sku-detail') ||
    p.startsWith('/exports')
  ) {
    open.workbench = true
  }
  if (
    name === 'Setup' ||
    p.startsWith('/setup') ||
    p === '/admin' ||
    p.startsWith('/admin/')
  ) {
    open.setup = true
  }
}

watch(
  () => route.path,
  () => syncOpenFromRoute(),
  { immediate: true }
)
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
  color: var(--accent, #214a7d);
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
.nav-collapse-all {
  display: block;
  width: 100%;
  padding: 0.35rem 0.75rem;
  border: none;
  border-bottom: 1px solid rgb(226 232 240);
  background: rgb(248 250 252);
  color: rgb(71 85 105);
  font-size: 0.6875rem;
  font-weight: 500;
  cursor: pointer;
  text-align: center;
}
.nav-collapse-all:hover:not(:disabled) {
  background: rgb(241 245 249);
  color: var(--accent, #214a7d);
}
.nav-collapse-all:disabled {
  opacity: 0.45;
  cursor: not-allowed;
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
.nav-group {
  margin-bottom: 0.125rem;
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
.nav-group-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0.45rem 1rem;
  border: none;
  background: transparent;
  cursor: pointer;
  font: inherit;
  text-align: left;
  color: var(--text, #1a3c68);
  border-radius: 0;
  min-height: 2rem;
}
.nav-group-toggle:hover {
  background: rgb(248 250 252);
}
.nav-group-label {
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgb(100 116 139);
}
.nav-chevron {
  font-size: 0.5rem;
  color: rgb(100 116 139);
  transition: transform 0.15s ease;
  flex-shrink: 0;
  margin-left: 0.5rem;
}
.nav-chevron.open {
  transform: rotate(-180deg);
}
.nav-group-body {
  padding-bottom: 0.25rem;
}
.nav-item {
  display: flex;
  align-items: center;
  padding: 0.5rem 1rem;
  color: var(--text, #1a3c68);
  text-decoration: none;
  font-size: 0.875rem;
  border-left: 3px solid transparent;
  min-height: 2rem;
}
.nav-item--sub {
  padding-left: 1.25rem;
  font-size: 0.8125rem;
}
.nav-item:hover {
  background: rgb(248 250 252);
}
.nav-item.active {
  border-left-color: var(--accent, #214a7d);
  background: rgb(232 238 247);
  color: var(--accent-hover, #1a3c68);
  font-weight: 500;
}
.nav-item.active:hover {
  background: rgb(210 222 239);
}

.collapsed .nav-section {
  font-size: 0.5625rem;
  padding-left: 0.5rem;
  padding-right: 0.5rem;
}
.collapsed .nav-item {
  padding-left: 0.5rem;
  padding-right: 0.35rem;
  font-size: 0.6875rem;
  line-height: 1.25;
  white-space: normal;
}
.collapsed .nav-item--sub {
  padding-left: 0.65rem;
}
.collapsed .nav-group-body {
  padding-bottom: 0.125rem;
}
</style>
