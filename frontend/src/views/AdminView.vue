<template>
  <div class="admin-page">
    <div class="admin-tabs">
      <router-link
        v-for="tab in tabs"
        :key="tab.name"
        :to="tab.path"
        class="admin-tab"
        active-class="active"
      >
        {{ tab.label }}
      </router-link>
    </div>
    <div class="admin-tab-content">
      <router-view v-slot="{ Component }">
        <keep-alive>
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </div>
  </div>
</template>

<script setup lang="ts">
const tabs = [
  { name: 'AdminProducts', path: '/admin/products', label: 'Products' },
  { name: 'AdminWarehouses', path: '/admin/warehouses', label: 'Warehouses' },
  { name: 'AdminSuppliers', path: '/admin/suppliers', label: 'Suppliers' },
  { name: 'AdminLanes', path: '/admin/lanes', label: 'Lanes (Supplier → Warehouse)' },
  { name: 'AdminPolicies', path: '/admin/policies', label: 'Stock Rules' },
  { name: 'AdminTimelines', path: '/admin/timelines', label: 'Timelines' },
  { name: 'AdminForecastMethods', path: '/admin/forecast-methods', label: 'Forecasting Methods' },
  { name: 'AdminForecastEngine', path: '/admin/forecast-engine', label: 'Forecast Settings' },
  { name: 'AdminSettings', path: '/admin/settings', label: 'Settings' },
  { name: 'AdminImportFormats', path: '/admin/import-formats', label: 'Import Formats' },
  { name: 'AdminWarehouseProductCodes', path: '/admin/warehouse-product-codes', label: 'Warehouse Product Codes' },
]
</script>

<style scoped>
.admin-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.admin-tabs {
  display: flex;
  gap: 0.375rem;
  flex-shrink: 0;
  padding: 0.5rem 0.625rem;
  margin-bottom: 0.75rem;
  background: rgb(241 245 249);
  border: 1px solid rgb(226 232 240);
  border-radius: 0.5rem;
  box-shadow: inset 0 1px 0 0 rgb(255 255 255 / 0.6);
  overflow-x: auto;
  flex-wrap: nowrap;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin;
}
.admin-tab {
  padding: 0.5rem 0.875rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--text, #1a3c68);
  text-decoration: none;
  white-space: nowrap;
  border-radius: 0.375rem;
  border: 1px solid rgb(203 213 225);
  background: rgb(255 255 255);
  box-shadow: 0 1px 2px rgb(15 40 71 / 0.06);
  flex-shrink: 0;
  transition:
    background 0.12s ease,
    color 0.12s ease,
    border-color 0.12s ease,
    box-shadow 0.12s ease;
}
.admin-tab:hover {
  background: rgb(232 238 247);
  border-color: var(--accent, #214a7d);
  color: var(--accent-hover, #1a3c68);
  box-shadow: 0 1px 3px rgb(15 40 71 / 0.1);
}
.admin-tab.active {
  background: var(--table-header-bg, #153256);
  color: rgb(248 250 252);
  border-color: var(--table-header-bg, #153256);
  font-weight: 600;
  box-shadow: 0 1px 3px rgb(15 40 71 / 0.2);
}
.admin-tab.active:hover {
  background: var(--accent-hover, #1a3c68);
  border-color: var(--accent-hover, #1a3c68);
  color: rgb(255 255 255);
}
.admin-tab-content {
  flex: 1;
  overflow: auto;
  min-height: 0;
  padding: 1rem 0;
}
/* Tables scroll within tab; tab content can still grow */
.admin-tab-content :deep(.tab-table-section .app-table-wrap) {
  max-height: 50vh;
  overflow: auto;
}
</style>
