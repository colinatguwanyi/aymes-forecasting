<template>
  <div class="page-shell space-y-6">
    <header class="page-header">
      <h1>Forecast scenarios</h1>
      <p class="muted mt-1">Compare and manage planning scenarios tied to forecasts.</p>
    </header>
    <section class="card card-body text-sm">
      <p class="muted">
        Scenario planning for supply runs is available from
        <router-link to="/planning/scenario-manager" class="text-blue-600 hover:underline">Scenario Manager</router-link>.
        Forecast engine configuration is under
        <router-link to="/admin/forecast-engine" class="text-blue-600 hover:underline">Forecast Settings</router-link>.
      </p>
    </section>
  </div>
</template>

<script setup lang="ts"></script>
