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

/* ── Shared Markdown body styles ─────────────────────────────────────── */
.md-body h1 {
  font-size: 1.6rem;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.4rem;
  margin: 1.5rem 0 0.75rem;
}
.md-body h2 {
  font-size: 1.3rem;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.3rem;
  margin: 1.25rem 0 0.6rem;
}
.md-body h3 {
  font-size: 1.1rem;
  margin: 1rem 0 0.5rem;
}
.md-body p {
  margin: 0.6rem 0;
  line-height: 1.7;
}
.md-body ul,
.md-body ol {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}
.md-body li {
  margin: 0.3rem 0;
}
.md-body code {
  font-family: var(--font-mono);
  background: var(--bg-tertiary);
  padding: 0.15rem 0.35rem;
  border-radius: 4px;
  font-size: 0.88em;
}
.md-body pre {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem;
  overflow-x: auto;
  margin: 0.75rem 0;
}
.md-body pre code {
  background: none;
  padding: 0;
}
.md-body blockquote {
  border-left: 3px solid var(--accent);
  padding-left: 1rem;
  color: var(--text-secondary);
  margin: 0.75rem 0;
}
.md-body table {
  width: 100%;
  border-collapse: collapse;
  margin: 0.75rem 0;
}
.md-body th,
.md-body td {
  border: 1px solid var(--border);
  padding: 0.5rem 0.75rem;
  text-align: left;
}
.md-body th {
  background: var(--bg-tertiary);
  font-weight: 600;
}
.md-body a {
  color: var(--accent);
  word-break: break-all;
}
.md-body strong {
  color: var(--text-primary);
  font-weight: 600;
}
.md-body hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 1.5rem 0;
}
</style>
