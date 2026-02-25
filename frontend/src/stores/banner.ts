import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface BannerItem {
  id: string
  type: 'success' | 'error' | 'info'
  title: string
  message: string
  dismissible?: boolean
}

export const useBannerStore = defineStore('banner', () => {
  const items = ref<BannerItem[]>([])

  function add(banner: Omit<BannerItem, 'id'>) {
    const id = `banner-${Date.now()}-${Math.random().toString(36).slice(2)}`
    items.value.push({ ...banner, id, dismissible: banner.dismissible ?? true })
  }

  function dismiss(id: string) {
    items.value = items.value.filter((b) => b.id !== id)
  }

  return { items, add, dismiss }
})
