<script setup lang="ts">
</script>

<template>
  <div class="app-shell">
    <router-view />
  </div>
</template>

<style>
/* ── Reset & Global Tokens ─────────────────────────────────────────────── */
*,
*::before,
*::after {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

:root {
  /* Claude-inspired warm light theme */
  --bg-primary: #f5f0e8;
  --bg-secondary: #ece5d8;
  --bg-tertiary: #e3dace;
  --bg-card: #faf7f2;
  --border: #d4cabb;
  --border-light: #c5b9a8;
  --text-primary: #2d2418;
  --text-secondary: #6b5d4d;
  --text-muted: #9a8b78;
  --accent: #c26a3a;
  --accent-hover: #a8552a;
  --accent-dim: rgba(194, 106, 58, 0.12);
  --success: #3a7d44;
  --success-dim: rgba(58, 125, 68, 0.1);
  --warning: #b8860b;
  --warning-dim: rgba(184, 134, 11, 0.1);
  --error: #c0392b;
  --error-dim: rgba(192, 57, 43, 0.1);
  --radius: 8px;
  --radius-lg: 12px;
  --font-mono: "SF Mono", "Fira Code", "Cascadia Code", monospace;
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial,
    sans-serif;
}

html {
  font-size: 15px;
}

body {
  font-family: var(--font-sans);
  background: var(--bg-primary);
  color: var(--text-primary);
  line-height: 1.6;
  min-height: 100vh;
}

a {
  color: var(--accent);
  text-decoration: none;
}
a:hover {
  color: var(--accent-hover);
  text-decoration: underline;
}

.app-shell {
  min-height: 100vh;
}

/* ── Scrollbar ─────────────────────────────────────────────────────────── */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--border-light);
}
</style>
