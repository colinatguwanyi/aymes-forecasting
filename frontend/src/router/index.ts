import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'Dashboard', meta: { title: 'Dashboard' }, component: () => import('../views/DashboardView.vue') },
    { path: '/inventory-projection', name: 'InventoryProjection', meta: { title: 'Inventory Projection' }, component: () => import('../views/InventoryProjectionView.vue') },
    { path: '/planning-grid', name: 'WeeklyPlanningGrid', meta: { title: 'Weekly Planning Grid' }, component: () => import('../views/WeeklyPlanningGridView.vue') },
    { path: '/planned-orders', name: 'PlannedOrders', meta: { title: 'Planned Orders' }, component: () => import('../views/PlannedOrdersView.vue') },
    { path: '/admin', name: 'Admin', meta: { title: 'Admin' }, component: () => import('../views/AdminView.vue') },
    { path: '/imports', name: 'Imports', meta: { title: 'Imports' }, component: () => import('../views/ImportsView.vue') },
    { path: '/exports', name: 'Exports', meta: { title: 'Exports' }, component: () => import('../views/ExportsView.vue') },
  ],
})

export default router
