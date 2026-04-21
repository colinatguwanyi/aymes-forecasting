<template>
  <!-- WMS-style toolbar: primary actions left, filters centre, search right -->
  <div class="table-toolbar">
    <div v-if="$slots.leading" class="table-toolbar__leading">
      <slot name="leading" />
    </div>
    <div class="table-toolbar__filters">
      <slot name="filters" />
      <button
        v-if="hasActiveFilters"
        type="button"
        class="table-toolbar__clear"
        @click="$emit('clear')"
      >
        Clear filters
      </button>
    </div>
    <div class="table-toolbar__search">
      <span class="table-toolbar__search-icon" aria-hidden="true">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </span>
      <input
        :value="modelValue"
        type="search"
        :placeholder="searchPlaceholder"
        class="table-toolbar__input"
        @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
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

<style scoped>
.table-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1rem;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
  background: rgb(248 250 252);
  border: 1px solid rgb(226 232 240);
  border-radius: 0.5rem;
  box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.04);
}
.table-toolbar__leading {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}
.table-toolbar__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  flex: 1 1 auto;
  min-width: 0;
}
.table-toolbar__clear {
  font-size: 0.8125rem;
  color: var(--accent, #214a7d);
  background: transparent;
  border: none;
  padding: 0.25rem 0.5rem;
  border-radius: 0.375rem;
  cursor: pointer;
}
.table-toolbar__clear:hover {
  background: rgb(232 238 247);
}
.table-toolbar__search {
  position: relative;
  flex: 1 1 200px;
  max-width: 22rem;
  min-width: 160px;
}
.table-toolbar__search-icon {
  position: absolute;
  left: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  color: rgb(100 116 139);
  pointer-events: none;
  display: flex;
}
.table-toolbar__input {
  width: 100%;
  padding: 0.5rem 0.75rem 0.5rem 2.25rem;
  font-size: 0.875rem;
  border: 1px solid rgb(203 213 225);
  border-radius: 0.375rem;
  background: #fff;
  color: var(--text, #1a3c68);
  outline: none;
}
.table-toolbar__input:focus {
  border-color: var(--accent, #214a7d);
  box-shadow: 0 0 0 2px rgba(33, 74, 125, 0.2);
}
.table-toolbar__input::placeholder {
  color: rgb(148 163 184);
}
</style>
