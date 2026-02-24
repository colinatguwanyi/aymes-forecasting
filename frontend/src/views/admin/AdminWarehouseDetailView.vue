<template>
  <div v-if="warehouse" class="space-y-6">
    <PageHeader
      :title="warehouse.code"
      :breadcrumbs="[
        { label: 'Admin', path: '/admin' },
        { label: 'Warehouses', path: '/admin/warehouses' },
      ]"
    >
      <template #actions>
        <router-link
          :to="{ name: 'AdminWarehouses' }"
          class="px-4 py-2 text-sm font-medium text-neutral-700 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50"
        >
          Back to list
        </router-link>
      </template>
    </PageHeader>
    <div class="bg-white border border-neutral-200 rounded-lg p-6">
      <dl class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
        <div><dt class="text-neutral-500">Code</dt><dd class="font-medium mt-0.5">{{ warehouse.code }}</dd></div>
        <div><dt class="text-neutral-500">Name</dt><dd class="font-medium mt-0.5">{{ warehouse.name ?? '—' }}</dd></div>
        <div><dt class="text-neutral-500">Status</dt><dd class="font-medium mt-0.5">{{ warehouse.active ? 'Active' : 'Inactive' }}</dd></div>
      </dl>
    </div>
  </div>
  <div v-else class="py-12 text-center text-neutral-500">Warehouse not found.</div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import PageHeader from '@/components/console/PageHeader.vue'

const route = useRoute()
const store = useAdminStore()
const warehouse = computed(() => store.warehouses.find((w) => w.id === Number(route.params.id)) ?? null)
onMounted(() => store.fetchWarehouses())
</script>
