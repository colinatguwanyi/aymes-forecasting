<template>
  <div class="app">
    <nav class="nav">
      <router-link to="/">Dashboard</router-link>
      <router-link to="/inventory-projection">Inventory Projection</router-link>
      <router-link to="/planned-orders">Planned Orders</router-link>
      <router-link to="/admin">Admin</router-link>
      <router-link to="/imports">Imports</router-link>
      <router-link to="/exports">Exports</router-link>
    </nav>
    <main class="main">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
</script>

<style>
:root {
  --bg: #0f1419;
  --surface: #1a2332;
  --border: #2d3a4f;
  --text: #e6edf3;
  --muted: #8b949e;
  --accent: #58a6ff;
  --danger: #f85149;
  --success: #3fb950;
  --radius: 8px;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); }
.app { min-height: 100vh; display: flex; flex-direction: column; }
.nav {
  display: flex; gap: 0.5rem; padding: 0.75rem 1rem; background: var(--surface); border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.nav a { color: var(--accent); text-decoration: none; padding: 0.25rem 0.5rem; border-radius: var(--radius); }
.nav a:hover { background: var(--border); }
.nav a.router-link-active { background: var(--border); color: var(--text); }
.main { flex: 1; padding: 1rem; max-width: 1400px; margin: 0 auto; width: 100%; }
</style>
