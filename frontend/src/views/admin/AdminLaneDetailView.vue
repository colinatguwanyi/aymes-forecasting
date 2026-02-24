<template>
  <div v-if="lane" class="space-y-6">
    <PageHeader
      title="Lane"
      :breadcrumbs="[
        { label: 'Admin', path: '/admin' },
        { label: 'Lanes', path: '/admin/lanes' },
      ]"
    >
      <template #actions>
        <router-link
          :to="{ name: 'AdminLanes' }"
          class="px-4 py-2 text-sm font-medium text-neutral-700 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50"
        >
          Back to list
        </router-link>
      </template>
    </PageHeader>
    <div class="bg-white border border-neutral-200 rounded-lg p-6">
      <dl class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
        <div><dt class="text-neutral-500">Supplier</dt><dd class="font-medium mt-0.5">{{ supplierName(lane.supplier_id) }}</dd></div>
        <div><dt class="text-neutral-500">Warehouse</dt><dd class="font-medium mt-0.5">{{ warehouseName(lane.warehouse_id) }}</dd></div>
        <div><dt class="text-neutral-500">Lane code</dt><dd class="font-medium mt-0.5">{{ lane.code ?? '—' }}</dd></div>
      </dl>
    </div>
  </div>
  <div v-else class="py-12 text-center text-neutral-500">Lane not found.</div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import PageHeader from '@/components/console/PageHeader.vue'

const route = useRoute()
const store = useAdminStore()
const lane = computed(() => store.lanes.find((l) => l.id === Number(route.params.id)) ?? null)
function supplierName(id: number) {
  const s = store.suppliers.find((x) => x.id === id)
  return s ? `${s.code} – ${s.name ?? ''}`.trim() : String(id)
}
function warehouseName(id: number) {
  const w = store.warehouses.find((x) => x.id === id)
  return w ? `${w.code} – ${w.name ?? ''}`.trim() : String(id)
}
onMounted(async () => {
  await Promise.all([store.fetchLanes(), store.fetchSuppliers(), store.fetchWarehouses()])
})
</script>
