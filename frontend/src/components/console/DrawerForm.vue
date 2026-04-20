<template>
  <Teleport to="body">
    <Transition name="drawer">
      <div
        v-if="modelValue"
        class="fixed inset-0 z-50 flex justify-end"
        aria-modal="true"
        role="dialog"
        aria-labelledby="drawer-title"
      >
        <div class="absolute inset-0 bg-neutral-900/30" aria-hidden="true" @click="close" />
        <aside
          class="relative w-full max-w-md bg-white shadow-xl flex flex-col max-h-full overflow-hidden"
          @click.stop
        >
          <div class="flex items-center justify-between px-6 py-4 border-b border-neutral-200">
            <h2 id="drawer-title" class="text-lg font-semibold text-neutral-900">
              {{ title }}
            </h2>
            <button
              type="button"
              class="p-2 rounded-lg text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700"
              aria-label="Close"
              @click="close"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
          <div class="flex-1 overflow-y-auto px-6 py-4">
            <slot />
          </div>
          <div v-if="$slots.footer" class="flex items-center justify-end gap-2 px-6 py-4 border-t border-neutral-200 bg-neutral-50">
            <slot name="footer" />
          </div>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: boolean
  title: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

function close() {
  emit('update:modelValue', false)
}
</script>

<style scoped>
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.2s ease;
}
.drawer-enter-active aside,
.drawer-leave-active aside {
  transition: transform 0.25s ease;
}
.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}
.drawer-enter-from aside,
.drawer-leave-to aside {
  transform: translateX(100%);
}
</style>
