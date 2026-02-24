<template>
  <div v-if="product" class="space-y-6">
    <PageHeader
      :title="product.sku"
      :breadcrumbs="[
        { label: 'Admin', path: '/admin' },
        { label: 'Products', path: '/admin/products' },
      ]"
    >
      <template #actions>
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-neutral-700 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50"
          @click="$router.push({ name: 'AdminProducts' })"
        >
          Back to list
        </button>
      </template>
    </PageHeader>

    <div class="bg-white border border-neutral-200 rounded-lg p-6">
      <h2 class="text-sm font-medium text-neutral-500 mb-4">Summary</h2>
      <dl class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
        <div>
          <dt class="text-neutral-500">SKU</dt>
          <dd class="font-medium text-neutral-900 mt-0.5">{{ product.sku }}</dd>
        </div>
        <div>
          <dt class="text-neutral-500">Name</dt>
          <dd class="font-medium text-neutral-900 mt-0.5">{{ product.name ?? '—' }}</dd>
        </div>
        <div>
          <dt class="text-neutral-500">Description</dt>
          <dd class="font-medium text-neutral-900 mt-0.5">{{ product.description ?? '—' }}</dd>
        </div>
        <div>
          <dt class="text-neutral-500">Status</dt>
          <dd class="font-medium text-neutral-900 mt-0.5">{{ product.active ? 'Active' : 'Inactive' }}</dd>
        </div>
      </dl>
    </div>

    <div class="border border-neutral-200 rounded-lg bg-white overflow-hidden">
      <nav class="flex border-b border-neutral-200">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          :class="[
            'px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors',
            activeTab === tab.id
              ? 'border-neutral-700 text-neutral-900'
              : 'border-transparent text-neutral-500 hover:text-neutral-700',
          ]"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </nav>
      <div class="p-4">
        <div v-if="activeTab === 'overview'" class="overflow-x-auto">
          <table class="w-full text-sm border-collapse">
            <thead class="bg-neutral-50 border-b border-neutral-200">
              <tr>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">Field</th>
                <th class="px-3 py-2 text-left font-medium text-neutral-600">Value</th>
              </tr>
            </thead>
            <tbody>
              <tr class="border-b border-neutral-100"><td class="px-3 py-2 text-neutral-500">SKU</td><td class="px-3 py-2">{{ product.sku }}</td></tr>
              <tr class="border-b border-neutral-100"><td class="px-3 py-2 text-neutral-500">Name</td><td class="px-3 py-2">{{ product.name ?? '—' }}</td></tr>
              <tr class="border-b border-neutral-100"><td class="px-3 py-2 text-neutral-500">Description</td><td class="px-3 py-2">{{ product.description ?? '—' }}</td></tr>
              <tr class="border-b border-neutral-100"><td class="px-3 py-2 text-neutral-500">UOM</td><td class="px-3 py-2">{{ product.uom ?? '—' }}</td></tr>
              <tr class="border-b border-neutral-100"><td class="px-3 py-2 text-neutral-500">Active</td><td class="px-3 py-2">{{ product.active ? 'Yes' : 'No' }}</td></tr>
            </tbody>
          </table>
        </div>
        <div v-else-if="activeTab === 'history'" class="text-sm text-neutral-500 py-8 text-center">
          History (audit log) — coming soon.
        </div>
        <div v-else-if="activeTab === 'related'" class="text-sm text-neutral-500 py-8 text-center">
          Related (policies, lanes) — coming soon.
        </div>
      </div>
    </div>
  </div>
  <div v-else class="py-12 text-center text-neutral-500">
    Product not found.
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import PageHeader from '@/components/console/PageHeader.vue'

const route = useRoute()
const store = useAdminStore()

const product = computed(() => {
  const id = Number(route.params.id)
  return store.products.find((p) => p.id === id) ?? null
})

const activeTab = ref('overview')
const tabs = [
  { id: 'overview', label: 'Overview' },
  { id: 'history', label: 'History' },
  { id: 'related', label: 'Related' },
]

onMounted(() => store.fetchProducts())
</script>
