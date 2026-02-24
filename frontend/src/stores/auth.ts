import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchAuthMe, type AuthMeResponse } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const _me = ref<AuthMeResponse | null>(null)
  const _loading = ref(false)
  const _error = ref<string | null>(null)

  const authenticated = computed(() => _me.value?.authenticated ?? false)
  const user = computed(() => _me.value?.user ?? null)
  const roles = computed(() => _me.value?.roles ?? [])
  const authMode = computed(() => _me.value?.auth_mode ?? null)
  const loading = computed(() => _loading.value)
  const error = computed(() => _error.value)

  function can(role: string): boolean {
    return roles.value.includes(role)
  }

  function canAdmin(): boolean {
    return can('Admin')
  }

  function canPlanner(): boolean {
    return can('Admin') || can('Planner')
  }

  function canOperator(): boolean {
    return can('Admin') || can('Operator')
  }

  async function loadMe(): Promise<void> {
    _loading.value = true
    _error.value = null
    try {
      _me.value = await fetchAuthMe()
    } catch (e: unknown) {
      _me.value = null
      const msg = e instanceof Error ? e.message : String(e)
      const status = (e as { response?: { status?: number } })?.response?.status
      _error.value = status === 401 ? 'Not signed in' : msg
    } finally {
      _loading.value = false
    }
  }

  return {
    authenticated,
    user,
    roles,
    authMode,
    loading,
    error,
    can,
    canAdmin,
    canPlanner,
    canOperator,
    loadMe,
  }
})
