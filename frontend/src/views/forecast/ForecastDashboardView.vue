<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Forecast dashboard</h1>
      <p class="muted mt-1">Summary and shortcuts for forecast workflows.</p>
    </header>
    <section class="card card-body text-sm space-y-3">
      <p class="muted">
        Detailed run controls, source/runtime config, and diagnostics live under
        <router-link to="/admin/forecast-engine" class="text-blue-600 hover:underline">Settings · Forecast Settings</router-link>.
      </p>
      <ul class="list-disc pl-5 space-y-1">
        <li><router-link to="/forecast/runs" class="text-blue-600 hover:underline">Run forecast</router-link></li>
        <li><router-link to="/forecast/scenarios" class="text-blue-600 hover:underline">Scenarios</router-link></li>
        <li><router-link to="/forecast/exports" class="text-blue-600 hover:underline">Exports</router-link></li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts"></script>
