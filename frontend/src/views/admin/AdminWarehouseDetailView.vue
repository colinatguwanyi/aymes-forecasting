<template>
  <div v-if="loading" class="py-12 text-center text-neutral-500">Loading…</div>
  <div v-else-if="warehouse" class="space-y-6">
    <PageHeader
      :title="warehouse.code"
      :breadcrumbs="[
        { label: 'Admin', path: '/admin' },
        { label: 'Warehouses', path: '/admin/warehouses' },
      ]"
    >
      <template #actions>
        <router-link :to="{ name: 'AdminWarehouses' }" class="btn-secondary px-4 text-sm inline-flex items-center">Back to list</router-link>
      </template>
    </PageHeader>
    <div class="bg-white border border-neutral-200 rounded-lg p-6">
      <dl class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4 text-sm">
        <div><dt class="text-neutral-500">Code</dt><dd class="font-medium mt-0.5">{{ warehouse.code }}</dd></div>
        <div><dt class="text-neutral-500">Name</dt><dd class="font-medium mt-0.5">{{ warehouse.name ?? '—' }}</dd></div>
        <div><dt class="text-neutral-500">Timezone</dt><dd class="font-medium mt-0.5">{{ warehouse.timezone }}</dd></div>
        <div><dt class="text-neutral-500">Status</dt><dd class="font-medium mt-0.5">{{ warehouse.active ? 'Active' : 'Inactive' }}</dd></div>
        <div><dt class="text-neutral-500">Has stock (SOH / positions)</dt><dd class="font-medium mt-0.5">{{ warehouse.has_stock ? 'Yes' : 'No' }}</dd></div>
        <div><dt class="text-neutral-500">Site ownership</dt><dd class="font-medium mt-0.5">{{ warehouse.is_own_site ? 'AYMES / our site' : 'Other company / 3PL' }}</dd></div>
        <div><dt class="text-neutral-500">Site type</dt><dd class="font-medium mt-0.5">{{ siteTypeLabel(warehouse.site_type) }}</dd></div>
        <div class="sm:col-span-2">
          <dt class="text-neutral-500">Operator / 3PL name</dt>
          <dd class="font-medium mt-0.5">{{ warehouse.operator_name?.trim() ? warehouse.operator_name : '—' }}</dd>
        </div>
        <div class="sm:col-span-2">
          <dt class="text-neutral-500">Address</dt>
          <dd class="font-medium mt-0.5 whitespace-pre-wrap">{{ warehouse.address?.trim() ? warehouse.address : '—' }}</dd>
        </div>
      </dl>
    </div>
  </div>
  <div v-else class="py-12 text-center text-neutral-500">Warehouse not found.</div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api, { type Warehouse } from '@/api/client'
import PageHeader from '@/components/console/PageHeader.vue'

const route = useRoute()
const warehouse = ref<Warehouse | null>(null)
const loading = ref(true)

function siteTypeLabel(t: string): string {
  const m: Record<string, string> = {
    soh_warehouse: 'SOH at our warehouse',
    factory: 'Our factory',
    third_party_3pl: 'Third-party / 3PL',
  }
  return m[t] ?? t
}

onMounted(async () => {
  loading.value = true
  warehouse.value = null
  try {
    const id = Number(route.params.id)
    if (!Number.isFinite(id)) {
      loading.value = false
      return
    }
    const { data } = await api.get<Warehouse>(`/warehouses/${id}`)
    warehouse.value = data
  } catch {
    warehouse.value = null
  } finally {
    loading.value = false
  }
})
</script>
