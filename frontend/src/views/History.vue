<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useRouter } from "vue-router";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { fetchReports, fetchReport, deleteReport } from "../services/api";
import type { ReportSummary, ReportDetail } from "../types";

const router = useRouter();

const reports = ref<ReportSummary[]>([]);
const selectedReport = ref<ReportDetail | null>(null);
const loading = ref(false);
const error = ref("");

const renderedReport = computed(() => {
  if (!selectedReport.value) return "";
  return DOMPurify.sanitize(marked(selectedReport.value.report_markdown) as string);
});

onMounted(async () => {
  await loadReports();
});

async function loadReports() {
  loading.value = true;
  error.value = "";
  try {
    reports.value = await fetchReports();
  } catch (e: any) {
    error.value = e.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

async function viewReport(id: string) {
  loading.value = true;
  error.value = "";
  try {
    selectedReport.value = await fetchReport(id);
  } catch (e: any) {
    error.value = e.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

async function removeReport(id: string) {
  if (!confirm("确认删除此报告？")) return;
  try {
    await deleteReport(id);
    reports.value = reports.value.filter((r) => r.id !== id);
    if (selectedReport.value?.id === id) selectedReport.value = null;
  } catch (e: any) {
    error.value = e.message || "删除失败";
  }
}

function downloadReport() {
  if (!selectedReport.value) return;
  const blob = new Blob([selectedReport.value.report_markdown], {
    type: "text/markdown",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${selectedReport.value.topic}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
</script>

<template>
  <div class="history-view">
    <!-- Header -->
    <header class="history-header">
      <button class="btn-ghost" @click="router.push('/')">← 返回</button>
      <h2>历史报告</h2>
      <span class="report-count">{{ reports.length }} 份报告</span>
    </header>

    <p v-if="error" class="error-banner">{{ error }}</p>

    <div class="history-body">
      <!-- Report list -->
      <aside class="report-list-panel">
        <div v-if="loading && reports.length === 0" class="list-placeholder">
          加载中...
        </div>
        <div v-else-if="reports.length === 0" class="list-placeholder">
          暂无历史报告
        </div>
        <div
          v-for="r in reports"
          :key="r.id"
          class="report-card"
          :class="{ active: selectedReport?.id === r.id }"
          @click="viewReport(r.id)"
        >
          <div class="report-card-body">
            <span class="report-topic">{{ r.topic }}</span>
            <span class="report-date">{{ formatDate(r.created_at) }}</span>
          </div>
          <button
            class="btn-icon"
            title="删除"
            @click.stop="removeReport(r.id)"
          >
            &#x2715;
          </button>
        </div>
      </aside>

      <!-- Report content -->
      <main class="report-content-panel">
        <div v-if="!selectedReport" class="content-placeholder">
          选择一份报告查看
        </div>
        <template v-else>
          <div class="content-header">
            <div>
              <h3>{{ selectedReport.topic }}</h3>
              <span class="content-date">{{
                formatDate(selectedReport.created_at)
              }}</span>
            </div>
            <button class="btn-ghost btn-sm" @click="downloadReport">
              下载 Markdown
            </button>
          </div>
          <div class="md-body" v-html="renderedReport" />
        </template>
      </main>
    </div>
  </div>
</template>

<style scoped>
.history-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.history-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1.25rem;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.history-header h2 {
  font-size: 1.05rem;
  font-weight: 600;
}
.report-count {
  margin-left: auto;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.error-banner {
  background: var(--error-dim);
  color: var(--error);
  padding: 0.6rem 1rem;
  margin: 0.75rem 1.25rem 0;
  border-radius: var(--radius);
  font-size: 0.85rem;
}

.history-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ── List ───────────────────────────────────────────────────────────────── */
.report-list-panel {
  width: 340px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  overflow-y: auto;
  padding: 0.75rem;
}

.list-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 120px;
  color: var(--text-muted);
  font-size: 0.9rem;
}

.report-card {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  border-radius: var(--radius);
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 0.25rem;
}
.report-card:hover {
  background: var(--bg-tertiary);
}
.report-card.active {
  background: var(--accent-dim);
  border-left: 3px solid var(--accent);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.report-card-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.report-topic {
  font-size: 0.9rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.report-date {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 0.15rem;
}

.btn-icon {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 0.8rem;
  padding: 0.3rem;
  border-radius: 4px;
  transition: all 0.15s;
  flex-shrink: 0;
}
.btn-icon:hover {
  color: var(--error);
  background: var(--error-dim);
}

/* ── Content ───────────────────────────────────────────────────────────── */
.report-content-panel {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem 2rem;
  background: var(--bg-card);
}

.content-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--text-muted);
}

.content-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 1.5rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--border);
}
.content-header h3 {
  font-size: 1.25rem;
}
.content-date {
  font-size: 0.8rem;
  color: var(--text-muted);
}

/* ── Shared button styles ──────────────────────────────────────────────── */
.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.45rem 0.85rem;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-ghost:hover {
  color: var(--text-primary);
  border-color: var(--border-light);
}
.btn-sm {
  padding: 0.35rem 0.7rem;
  font-size: 0.8rem;
}

/* ── Markdown body (same as Research) ──────────────────────────────────── */
.md-body :deep(h1) {
  font-size: 1.6rem;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.4rem;
  margin: 1.5rem 0 0.75rem;
}
.md-body :deep(h2) {
  font-size: 1.3rem;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.3rem;
  margin: 1.25rem 0 0.6rem;
}
.md-body :deep(h3) {
  font-size: 1.1rem;
  margin: 1rem 0 0.5rem;
}
.md-body :deep(p) {
  margin: 0.6rem 0;
  line-height: 1.7;
}
.md-body :deep(ul),
.md-body :deep(ol) {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}
.md-body :deep(li) {
  margin: 0.3rem 0;
}
.md-body :deep(code) {
  font-family: var(--font-mono);
  background: var(--bg-tertiary);
  padding: 0.15rem 0.35rem;
  border-radius: 4px;
  font-size: 0.88em;
}
.md-body :deep(pre) {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem;
  overflow-x: auto;
  margin: 0.75rem 0;
}
.md-body :deep(pre code) {
  background: none;
  padding: 0;
}
.md-body :deep(blockquote) {
  border-left: 3px solid var(--accent);
  padding-left: 1rem;
  color: var(--text-secondary);
  margin: 0.75rem 0;
}
.md-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.75rem 0;
}
.md-body :deep(th),
.md-body :deep(td) {
  border: 1px solid var(--border);
  padding: 0.5rem 0.75rem;
  text-align: left;
}
.md-body :deep(th) {
  background: var(--bg-tertiary);
  font-weight: 600;
}
.md-body :deep(a) {
  color: var(--accent);
}
.md-body :deep(strong) {
  color: var(--text-primary);
  font-weight: 600;
}
.md-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: 1.5rem 0;
}
</style>
