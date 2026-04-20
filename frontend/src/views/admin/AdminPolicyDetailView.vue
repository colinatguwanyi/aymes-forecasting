<template>
  <div v-if="policy" class="space-y-6">
    <PageHeader
      :title="`${policy.sku} × ${policy.warehouse_code}`"
      :breadcrumbs="[
        { label: 'Admin', path: '/admin' },
        { label: 'Planning Policies', path: '/admin/policies' },
      ]"
    >
      <template #actions>
        <router-link
          :to="{ name: 'AdminPolicies' }"
          class="px-4 py-2 text-sm font-medium text-neutral-700 bg-white border border-neutral-300 rounded-lg hover:bg-neutral-50"
        >
          Back to list
        </router-link>
      </template>
    </PageHeader>
    <div class="bg-white border border-neutral-200 rounded-lg p-6">
      <dl class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
        <div><dt class="text-neutral-500">SKU</dt><dd class="font-medium mt-0.5">{{ policy.sku }}</dd></div>
        <div><dt class="text-neutral-500">Warehouse</dt><dd class="font-medium mt-0.5">{{ policy.warehouse_code }}</dd></div>
        <div><dt class="text-neutral-500">Mode</dt><dd class="font-medium mt-0.5">{{ policy.mode }}</dd></div>
        <div><dt class="text-neutral-500">Target weeks</dt><dd class="font-medium mt-0.5">{{ policy.target_weeks }}</dd></div>
      </dl>
    </div>
  </div>
  <div v-else class="py-12 text-center text-neutral-500">Policy not found.</div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAdminStore } from '@/stores/admin'
import PageHeader from '@/components/console/PageHeader.vue'

const route = useRoute()
const store = useAdminStore()
const policy = computed(() => store.planningPolicies.find((p) => p.id === Number(route.params.id)) ?? null)
onMounted(() => store.fetchPlanningPolicies())
</script>
