import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useLayoutStore = defineStore('layout', () => {
  const navCollapsed = ref(false)
  const rightPanelOpen = ref(false)
  const rightPanelTitle = ref('')
  const pageTitle = ref('')

  const navWidth = computed(() => (navCollapsed.value ? 64 : 232)) // px; matches CSS vars
  const rightPanelWidth = computed(() => (rightPanelOpen.value ? 380 : 0))

  function toggleNav() {
    navCollapsed.value = !navCollapsed.value
  }

  function openRightPanel(title: string) {
    rightPanelTitle.value = title
    rightPanelOpen.value = true
  }

  function closeRightPanel() {
    rightPanelOpen.value = false
  }

  function setPageTitle(title: string) {
    pageTitle.value = title
  }

  return {
    navCollapsed,
    rightPanelOpen,
    rightPanelTitle,
    pageTitle,
    navWidth,
    rightPanelWidth,
    toggleNav,
    openRightPanel,
    closeRightPanel,
    setPageTitle,
  }
})
