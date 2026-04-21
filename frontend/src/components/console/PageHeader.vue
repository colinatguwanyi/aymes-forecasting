<template>
  <header class="mb-6">
    <nav v-if="breadcrumbs?.length" class="flex items-center flex-wrap gap-x-1 gap-y-0.5 text-sm text-slate-500 mb-1" aria-label="Breadcrumb">
      <template v-for="crumb in breadcrumbs" :key="crumb.path">
        <router-link
          :to="crumb.path"
          class="hover:text-primary-700 transition-colors"
        >
          {{ crumb.label }}
        </router-link>
        <span class="text-slate-400 px-0.5 select-none" aria-hidden="true">&gt;</span>
      </template>
      <span class="text-primary-800 font-medium">{{ title }}</span>
    </nav>
    <div class="flex items-center justify-between gap-4 flex-wrap">
      <h1 class="text-xl font-semibold text-primary-900 tracking-tight">{{ title }}</h1>
      <div v-if="$slots.actions" class="flex items-center gap-2">
        <slot name="actions" />
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
export interface Breadcrumb {
  label: string
  path: string
}

defineProps<{
  title: string
  breadcrumbs?: Breadcrumb[]
}>()
</script>
