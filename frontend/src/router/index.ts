import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'Dashboard', meta: { title: 'Dashboard' }, component: () => import('../views/DashboardView.vue') },
    { path: '/stock-projection', name: 'StockProjection', meta: { title: 'Stock Projection' }, component: () => import('../views/StockProjectionView.vue') },
    { path: '/inventory-projection', name: 'InventoryProjection', meta: { title: 'Inventory Projection' }, component: () => import('../views/InventoryProjectionView.vue') },
    { path: '/planning-grid', name: 'WeeklyPlanningGrid', meta: { title: 'Weekly Planning Grid' }, component: () => import('../views/WeeklyPlanningGridView.vue') },
    { path: '/sku-detail', name: 'SkuDetail', meta: { title: 'SKU Detail' }, component: () => import('../views/SkuDetailView.vue') },
    { path: '/planned-orders', name: 'PlannedOrders', meta: { title: 'Planned Orders' }, component: () => import('../views/PlannedOrdersView.vue') },
    { path: '/stock-position', name: 'StockPosition', meta: { title: 'Stock Position' }, component: () => import('../views/StockPositionBreakdownView.vue') },
    { path: '/exceptions', name: 'Exceptions', meta: { title: 'Exceptions' }, component: () => import('../views/ExceptionsView.vue') },
    {
      path: '/admin',
      name: 'Admin',
      meta: { title: 'Admin' },
      component: () => import('../views/AdminView.vue'),
      redirect: { name: 'AdminProducts' },
      children: [
        { path: 'products', name: 'AdminProducts', meta: { title: 'Admin · Products' }, component: () => import('../views/admin/AdminProductsTab.vue') },
        { path: 'products/:id', name: 'AdminProductDetail', meta: { title: 'Admin · Product' }, component: () => import('../views/admin/AdminProductDetailView.vue') },
        { path: 'warehouses', name: 'AdminWarehouses', meta: { title: 'Admin · Warehouses' }, component: () => import('../views/admin/AdminWarehousesTab.vue') },
        { path: 'warehouses/:id', name: 'AdminWarehouseDetail', meta: { title: 'Admin · Warehouse' }, component: () => import('../views/admin/AdminWarehouseDetailView.vue') },
        { path: 'suppliers', name: 'AdminSuppliers', meta: { title: 'Admin · Suppliers' }, component: () => import('../views/admin/AdminSuppliersTab.vue') },
        { path: 'suppliers/:id', name: 'AdminSupplierDetail', meta: { title: 'Admin · Supplier' }, component: () => import('../views/admin/AdminSupplierDetailView.vue') },
        { path: 'lanes', name: 'AdminLanes', meta: { title: 'Admin · Lanes' }, component: () => import('../views/admin/AdminLanesTab.vue') },
        { path: 'lanes/:id', name: 'AdminLaneDetail', meta: { title: 'Admin · Lane' }, component: () => import('../views/admin/AdminLaneDetailView.vue') },
        { path: 'policies', name: 'AdminPolicies', meta: { title: 'Admin · Planning Policies' }, component: () => import('../views/admin/AdminPoliciesTab.vue') },
        { path: 'policies/:id', name: 'AdminPolicyDetail', meta: { title: 'Admin · Policy' }, component: () => import('../views/admin/AdminPolicyDetailView.vue') },
        { path: 'timelines', name: 'AdminTimelines', meta: { title: 'Admin · Timelines' }, component: () => import('../views/admin/AdminTimelinesView.vue') },
      ],
    },
    { path: '/imports', name: 'Imports', meta: { title: 'Imports' }, component: () => import('../views/ImportsView.vue') },
    { path: '/reports', name: 'Reports', meta: { title: 'Reports' }, component: () => import('../views/ReportsView.vue') },
    { path: '/exports', name: 'Exports', meta: { title: 'Exports' }, component: () => import('../views/ExportsView.vue') },
  ],
})

export default router
