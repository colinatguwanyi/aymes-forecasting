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
  { name: 'AdminPolicies', path: '/admin/policies', label: 'Planning Policies' },
  { name: 'AdminTimelines', path: '/admin/timelines', label: 'Timelines' },
  { name: 'AdminForecastMethods', path: '/admin/forecast-methods', label: 'Forecasting Methods' },
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
  gap: 0;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--main-bg);
}
.admin-tab {
  padding: 0.6rem 1rem;
  font-size: 0.875rem;
  color: var(--muted);
  text-decoration: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.admin-tab:hover {
  color: var(--text);
}
.admin-tab.active {
  color: var(--accent);
  font-weight: 500;
  border-bottom-color: var(--accent);
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
