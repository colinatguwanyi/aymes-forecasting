<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Run forecast</h1>
      <p class="muted mt-1">Create runs, execute models, and inspect results.</p>
    </header>
    <section class="card card-body text-sm">
      <p class="muted">
        Use
        <router-link to="/admin/forecast-engine" class="text-blue-600 hover:underline">Forecast Settings</router-link>
        for the full run console (create run, execute, supply-adjusted output, exports).
      </p>
    </section>
  </div>
</template>

<script setup lang="ts"></script>
