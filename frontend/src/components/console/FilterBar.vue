<template>
  <div class="flex flex-wrap items-center gap-3 py-3 px-4 bg-white border border-neutral-200 rounded-lg mb-4">
    <div class="relative flex-1 min-w-[180px] max-w-sm">
      <span class="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400 pointer-events-none" aria-hidden="true">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
      </span>
      <input
        :value="modelValue"
        type="search"
        :placeholder="searchPlaceholder"
        class="w-full pl-9 pr-3 py-2 text-sm border border-neutral-300 rounded-md focus:ring-2 focus:ring-neutral-400 focus:border-neutral-500 outline-none"
        @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <slot name="filters" />
      <button
        v-if="hasActiveFilters"
        type="button"
        class="text-sm text-neutral-600 hover:text-neutral-900 px-2 py-1 rounded hover:bg-neutral-100"
        @click="$emit('clear')"
      >
        Clear filters
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: string
  searchPlaceholder?: string
  hasActiveFilters?: boolean
}>()

defineEmits<{
  'update:modelValue': [value: string]
  clear: []
}>()
</script>
