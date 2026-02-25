<template>
  <div class="no-data-with-reason">
    <p class="no-data-title">{{ title }}</p>
    <ul v-if="reasons.length" class="reasons-list">
      <li v-for="(r, i) in reasons" :key="i">{{ r }}</li>
    </ul>
    <div v-if="actions.length" class="actions">
      <router-link
        v-for="(a, i) in actions"
        :key="i"
        :to="a.href"
        class="action-btn"
      >{{ a.label }}</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  reasons: string[]
  actions: { label: string; href: string }[]
}>()
</script>

<style scoped>
.no-data-with-reason {
  padding: 1.5rem;
  background: rgb(255 251 235);
  border: 1px solid rgb(253 224 71);
  border-radius: 0.5rem;
  color: rgb(120 53 15);
}
.no-data-title {
  font-weight: 600;
  margin: 0 0 0.5rem;
}
.reasons-list {
  margin: 0.5rem 0 1rem;
  padding-left: 1.25rem;
}
.reasons-list li {
  margin: 0.25rem 0;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.action-btn {
  display: inline-block;
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
  font-weight: 500;
  color: rgb(120 53 15);
  background: white;
  border: 1px solid rgb(253 224 71);
  border-radius: 0.375rem;
  text-decoration: none;
}
.action-btn:hover {
  background: rgb(254 249 195);
}
</style>
