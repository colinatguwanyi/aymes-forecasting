<template>
  <section
    v-if="content"
    class="rounded-lg border border-slate-200 bg-slate-50/80 text-slate-800 mb-4"
    aria-label="Page help"
  >
    <button
      type="button"
      class="w-full flex items-center justify-between gap-3 px-4 py-3 text-left text-sm font-medium text-slate-800 hover:bg-slate-100/90 rounded-lg transition-colors"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <span>How to use this page</span>
      <span class="text-slate-500 shrink-0" aria-hidden="true">{{ expanded ? '▼' : '▶' }}</span>
    </button>
    <div v-show="expanded" class="px-4 pb-4 pt-0 text-sm border-t border-slate-200/80">
      <h2 class="sr-only">{{ content.title }} — help</h2>
      <div
        v-if="content.planning_workflow"
        class="mt-3 pb-3 border-b border-slate-200/80"
      >
        <h3 class="font-medium text-slate-800 mb-1">Planning workflow</h3>
        <p
          v-if="content.planning_workflow.intro"
          class="text-slate-600 leading-snug mb-2"
        >
          {{ content.planning_workflow.intro }}
        </p>
        <ol class="list-decimal list-inside text-slate-600 leading-snug space-y-1 mb-3">
          <li v-for="(line, i) in content.planning_workflow.steps" :key="i">{{ line }}</li>
        </ol>
        <div class="space-y-1.5 text-slate-600 leading-snug">
          <p>
            <span class="font-medium text-slate-700">Stock-aware:</span>
            {{ content.planning_workflow.stock_aware }}
          </p>
          <p>
            <span class="font-medium text-slate-700">Demand-only:</span>
            {{ content.planning_workflow.demand_only }}
          </p>
        </div>
      </div>
      <dl class="space-y-3 mt-3">
        <div>
          <dt class="font-medium text-slate-700">What it’s for</dt>
          <dd class="mt-0.5 text-slate-600 leading-snug">{{ content.purpose }}</dd>
        </div>
        <div>
          <dt class="font-medium text-slate-700">When to use it</dt>
          <dd class="mt-0.5 text-slate-600 leading-snug">{{ content.when_to_use }}</dd>
        </div>
        <div v-if="content.key_actions.length">
          <dt class="font-medium text-slate-700">Main actions</dt>
          <dd class="mt-0.5">
            <ul class="list-disc list-inside text-slate-600 leading-snug space-y-1">
              <li v-for="(line, i) in content.key_actions" :key="i">{{ line }}</li>
            </ul>
          </dd>
        </div>
        <div v-if="content.next_steps.length">
          <dt class="font-medium text-slate-700">What to do next</dt>
          <dd class="mt-0.5">
            <ul class="list-disc list-inside text-slate-600 leading-snug space-y-1">
              <li v-for="(line, i) in content.next_steps" :key="i">{{ line }}</li>
            </ul>
          </dd>
        </div>
        <div v-if="content.important_notes">
          <dt class="font-medium text-amber-900">Note</dt>
          <dd class="mt-0.5 text-amber-950/90 leading-snug">{{ content.important_notes }}</dd>
        </div>
      </dl>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { getPageHelp, type PageHelpContent } from '@/config/pageHelp'

const props = defineProps<{
  /** Vue Router route name, e.g. 'Dashboard' */
  pageKey: string
}>()

const expanded = ref(false)

const content = computed<PageHelpContent | null>(() => getPageHelp(props.pageKey))
</script>
