import { ref, watch, type Ref } from 'vue'

/**
 * Debounced ref: mirrors source ref after `ms` of no changes.
 */
export function useDebounce<T>(source: Ref<T>, ms: number): Ref<T> {
  const debounced = ref(source.value) as Ref<T>
  let timeout: ReturnType<typeof setTimeout> | null = null
  watch(source, (v) => {
    if (timeout) clearTimeout(timeout)
    timeout = setTimeout(() => {
      debounced.value = v
      timeout = null
    }, ms)
  })
  return debounced
}
