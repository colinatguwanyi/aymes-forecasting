<template>
  <header class="mb-6">
    <nav v-if="breadcrumbs?.length" class="flex items-center gap-2 text-sm text-neutral-500 mb-1" aria-label="Breadcrumb">
      <router-link
        v-for="crumb in breadcrumbs"
        :key="crumb.path"
        :to="crumb.path"
        class="hover:text-neutral-700 transition-colors"
      >
        {{ crumb.label }}
      </router-link>
      <span class="text-neutral-400">/</span>
      <span class="text-neutral-700 font-medium">{{ title }}</span>
    </nav>
    <div class="flex items-center justify-between gap-4 flex-wrap">
      <h1 class="text-xl font-semibold text-neutral-900 tracking-tight">{{ title }}</h1>
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
