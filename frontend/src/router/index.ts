import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'Dashboard', component: () => import('../views/DashboardView.vue') },
    { path: '/inventory-projection', name: 'InventoryProjection', component: () => import('../views/InventoryProjectionView.vue') },
    { path: '/planned-orders', name: 'PlannedOrders', component: () => import('../views/PlannedOrdersView.vue') },
    { path: '/admin', name: 'Admin', component: () => import('../views/AdminView.vue') },
    { path: '/imports', name: 'Imports', component: () => import('../views/ImportsView.vue') },
    { path: '/exports', name: 'Exports', component: () => import('../views/ExportsView.vue') },
  ],
})

export default router
