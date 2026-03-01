<script setup lang="ts">
import { ref, computed, nextTick, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { runResearchStream } from "../services/api";
import type { TaskView, ActivityLog, SourceItem, SSEEvent } from "../types";

const router = useRouter();

// ── State ─────────────────────────────────────────────────────────────────
const topic = ref("");
const searchApi = ref("tavily");
const phase = ref<"input" | "researching" | "done">("input");
const error = ref("");

const tasks = ref<TaskView[]>([]);
const activityLogs = ref<ActivityLog[]>([]);
const reportMarkdown = ref("");
const reportId = ref<string | null>(null);
const langsmithUrl = ref<string | null>(null);

const selectedTaskId = ref<number | null>(null);
let logCounter = 0;
let abortController: AbortController | null = null;

// ── Computed ──────────────────────────────────────────────────────────────
const completedCount = computed(
  () => tasks.value.filter((t) => t.status === "completed" || t.status === "summarized").length
);
const totalCount = computed(() => tasks.value.length);
const progressPct = computed(() =>
  totalCount.value ? (completedCount.value / totalCount.value) * 100 : 0
);
const selectedTask = computed(() =>
  tasks.value.find((t) => t.id === selectedTaskId.value)
);

const renderedReport = computed(() => {
  if (!reportMarkdown.value) return "";
  return DOMPurify.sanitize(marked(reportMarkdown.value) as string);
});

// ── Activity logger ─────────────────────────────────────────────────────
function addLog(
  message: string,
  type: ActivityLog["type"] = "info",
  taskId?: number
) {
  activityLogs.value.push({
    id: ++logCounter,
    message,
    type,
    taskId,
    time: new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }),
  });
  nextTick(() => {
    const el = document.querySelector(".activity-log");
    if (el) el.scrollTop = el.scrollHeight;
  });
}

// ── Event handlers ──────────────────────────────────────────────────────
function handleSSE(event: SSEEvent) {
  switch (event.type) {
    case "status":
      {
        let logType: ActivityLog["type"] = "info";
        if (event.message.startsWith("SearchAgent:")) logType = "search";
        else if (event.message.startsWith("SummarizerAgent:")) logType = "summarize";
        else if (event.message.startsWith("EvaluatorAgent:")) logType = "evaluate";
        else if (event.message.startsWith("ReporterAgent:")) logType = "report";
        addLog(event.message, logType, event.task_id);
      }
      break;

    case "todo_list":
      tasks.value = event.tasks.map((t) => ({
        id: t.id,
        title: t.title,
        intent: t.intent,
        query: t.query,
        status: "pending",
        summary: "",
        sources: [],
      }));
      addLog(`已规划 ${event.tasks.length} 个研究子任务`, "info");
      break;

    case "task_status":
      {
        const task = tasks.value.find((t) => t.id === event.task_id);
        if (task) {
          task.status = event.status as TaskView["status"];
        }
        if (event.status === "in_progress" && selectedTaskId.value === null) {
          selectedTaskId.value = event.task_id;
        }
      }
      break;

    case "sources":
      {
        const task = tasks.value.find((t) => t.id === event.task_id);
        if (task) {
          task.sources = (event.sources as SourceItem[]) || [];
        }
      }
      break;

    case "task_summary_chunk":
      {
        const task = tasks.value.find((t) => t.id === event.task_id);
        if (task) {
          task.summary += event.content;
        }
        // auto-select this task if none selected
        if (selectedTaskId.value === null) {
          selectedTaskId.value = event.task_id;
        }
      }
      break;

    case "task_summary_clear":
      {
        const task = tasks.value.find((t) => t.id === event.task_id);
        if (task) task.summary = "";
      }
      break;

    case "report_chunk":
      reportMarkdown.value += event.content;
      break;

    case "final_report":
      reportMarkdown.value = event.report;
      reportId.value = event.report_id;
      addLog("研究报告生成完毕", "report");
      break;

    case "langsmith_url":
      langsmithUrl.value = event.url;
      break;

    case "error":
      error.value = event.detail;
      addLog(`错误: ${event.detail}`, "error");
      break;

    case "done":
      phase.value = "done";
      addLog("研究完成", "info");
      break;
  }
}

// ── Actions ─────────────────────────────────────────────────────────────
async function startResearch() {
  if (!topic.value.trim()) return;

  error.value = "";
  tasks.value = [];
  activityLogs.value = [];
  reportMarkdown.value = "";
  reportId.value = null;
  langsmithUrl.value = null;
  selectedTaskId.value = null;
  logCounter = 0;
  phase.value = "researching";

  abortController = new AbortController();
  addLog(`开始研究：${topic.value}`, "info");

  try {
    await runResearchStream(
      { topic: topic.value, search_api: searchApi.value },
      handleSSE,
      abortController.signal
    );
  } catch (e: any) {
    if (e.name !== "AbortError") {
      error.value = e.message || "未知错误";
      addLog(`请求失败: ${error.value}`, "error");
    }
    if (phase.value === "researching") phase.value = "done";
  }
}

function cancelResearch() {
  abortController?.abort();
  addLog("已取消研究", "info");
  phase.value = "done";
}

function newResearch() {
  phase.value = "input";
  topic.value = "";
  tasks.value = [];
  activityLogs.value = [];
  reportMarkdown.value = "";
  error.value = "";
  langsmithUrl.value = null;
  selectedTaskId.value = null;
}

function downloadReport() {
  if (!reportMarkdown.value) return;
  const blob = new Blob([reportMarkdown.value], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${topic.value || "report"}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

function getStatusIcon(status: string) {
  switch (status) {
    case "completed":
      return "\u2713";
    case "summarized":
      return "\u25C9";
    case "in_progress":
      return "\u25CB";
    case "failed":
      return "\u2717";
    default:
      return "\u2022";
  }
}

function getStatusLabel(status: string) {
  switch (status) {
    case "completed":
      return "已完成";
    case "summarized":
      return "已总结";
    case "in_progress":
      return "进行中";
    case "failed":
      return "失败";
    case "pending":
      return "待开始";
    default:
      return status;
  }
}

function getLogIcon(type: string) {
  switch (type) {
    case "search":
      return "\uD83D\uDD0D";
    case "summarize":
      return "\uD83D\uDCDD";
    case "evaluate":
      return "\uD83D\uDD04";
    case "report":
      return "\uD83D\uDCCA";
    case "error":
      return "\u26A0\uFE0F";
    default:
      return "\u25CF";
  }
}

onBeforeUnmount(() => {
  abortController?.abort();
});
</script>

<template>
  <!-- ── Input phase ───────────────────────────────────────────────── -->
  <div v-if="phase === 'input'" class="input-view">
    <div class="hero">
      <h1 class="hero-title">AutoResearch</h1>
      <p class="hero-sub">LangGraph-Powered Deep Research Assistant</p>
    </div>

    <div class="input-card">
      <textarea
        v-model="topic"
        class="topic-input"
        placeholder="输入你想深入研究的主题..."
        rows="3"
        maxlength="500"
        @keydown.meta.enter="startResearch"
        @keydown.ctrl.enter="startResearch"
      />
      <div class="input-actions">
        <select v-model="searchApi" class="search-select">
          <option value="tavily">Tavily</option>
          <option value="duckduckgo">DuckDuckGo</option>
          <option value="mcp">MCP Server</option>
        </select>
        <button class="btn-primary" :disabled="!topic.trim()" @click="startResearch">
          开始研究
        </button>
      </div>
      <p v-if="error" class="error-msg">{{ error }}</p>
    </div>

    <button class="link-btn history-link" @click="router.push('/history')">
      查看历史报告
    </button>
  </div>

  <!-- ── Research / Done phase ─────────────────────────────────────── -->
  <div v-else class="research-view">
    <!-- Header -->
    <header class="research-header">
      <div class="header-left">
        <h2 class="header-topic">{{ topic }}</h2>
        <div class="progress-bar-wrap">
          <div class="progress-bar" :style="{ width: progressPct + '%' }" />
        </div>
        <span class="progress-label">{{ completedCount }}/{{ totalCount }}</span>
      </div>
      <div class="header-actions">
        <button v-if="phase === 'researching'" class="btn-ghost" @click="cancelResearch">
          取消
        </button>
        <template v-else>
          <a
            v-if="langsmithUrl"
            :href="langsmithUrl"
            target="_blank"
            rel="noopener noreferrer"
            class="btn-ghost btn-trace"
          >
            View Trace
          </a>
          <button class="btn-ghost" @click="router.push('/history')">历史</button>
          <button class="btn-ghost" @click="downloadReport" :disabled="!reportMarkdown">
            下载
          </button>
          <button class="btn-primary btn-sm" @click="newResearch">新研究</button>
        </template>
      </div>
    </header>

    <div class="research-body">
      <!-- Left Panel: Activity + Tasks -->
      <aside class="left-panel">
        <!-- Activity Log -->
        <section class="panel-section">
          <h3 class="section-title">执行日志</h3>
          <div class="activity-log">
            <div
              v-for="log in activityLogs"
              :key="log.id"
              class="log-entry"
              :class="'log-' + log.type"
            >
              <span class="log-icon">{{ getLogIcon(log.type) }}</span>
              <span class="log-msg">{{ log.message }}</span>
              <span class="log-time">{{ log.time }}</span>
            </div>
            <div v-if="phase === 'researching'" class="log-entry log-active">
              <span class="pulse-dot" />
              <span class="log-msg">处理中...</span>
            </div>
          </div>
        </section>

        <!-- Task List -->
        <section class="panel-section">
          <h3 class="section-title">研究任务</h3>
          <div class="task-list">
            <div
              v-for="task in tasks"
              :key="task.id"
              class="task-card"
              :class="{
                active: task.id === selectedTaskId,
                ['status-' + task.status]: true,
              }"
              @click="selectedTaskId = task.id"
            >
              <span class="task-icon" :class="'icon-' + task.status">{{
                getStatusIcon(task.status)
              }}</span>
              <div class="task-info">
                <span class="task-title">{{ task.title }}</span>
                <span class="task-intent">{{ task.intent }}</span>
              </div>
            </div>
          </div>
        </section>
      </aside>

      <!-- Right Panel: Detail -->
      <main class="right-panel">
        <p v-if="error" class="error-banner">{{ error }}</p>

        <!-- Task Detail -->
        <section v-if="selectedTask" class="detail-section">
          <div class="detail-header">
            <h3>{{ selectedTask.title }}</h3>
            <span class="badge" :class="'badge-' + selectedTask.status">{{
              getStatusLabel(selectedTask.status)
            }}</span>
          </div>
          <p class="detail-meta">
            <strong>意图:</strong> {{ selectedTask.intent }}<br />
            <strong>查询:</strong> {{ selectedTask.query }}
          </p>

          <!-- Sources -->
          <div v-if="selectedTask.sources.length" class="sources-block">
            <h4>参考来源</h4>
            <div class="source-chips">
              <a
                v-for="(src, i) in selectedTask.sources"
                :key="i"
                :href="src.url || 'javascript:void(0)'"
                :target="src.url ? '_blank' : undefined"
                class="source-chip"
                :class="{ 'no-link': !src.url }"
                :title="src.content"
                @click="!src.url && $event.preventDefault()"
              >
                {{ src.title || src.url || '未知来源' }}
              </a>
            </div>
          </div>

          <!-- Status hint while task is working -->
          <div
            v-if="selectedTask.status === 'in_progress'"
            class="summary-placeholder"
          >
            <span class="typing-indicator">
              <span /><span /><span />
            </span>
            正在搜索并分析中...
          </div>
          <div
            v-else-if="selectedTask.status === 'summarized'"
            class="summary-placeholder"
          >
            已完成分析，等待报告生成...
          </div>
        </section>

        <!-- Report -->
        <section v-if="reportMarkdown" class="report-section">
          <div class="report-header">
            <h3>研究报告</h3>
            <button
              class="btn-ghost btn-sm"
              @click="downloadReport"
            >
              下载 Markdown
            </button>
          </div>
          <div class="md-body report-body" v-html="renderedReport" />
        </section>

        <!-- Placeholder when nothing is selected -->
        <div
          v-if="!selectedTask && !reportMarkdown && tasks.length === 0"
          class="empty-state"
        >
          <p>等待研究任务规划...</p>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
/* ── Input View ────────────────────────────────────────────────────────── */
.input-view {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 2rem;
}

.hero {
  text-align: center;
  margin-bottom: 2.5rem;
}
.hero-title {
  font-size: 2.8rem;
  font-weight: 700;
  background: linear-gradient(135deg, var(--accent), var(--warning));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.hero-sub {
  color: var(--text-secondary);
  margin-top: 0.5rem;
  font-size: 1.05rem;
}

.input-card {
  width: 100%;
  max-width: 600px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 1.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.topic-input {
  width: 100%;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-primary);
  font-size: 1rem;
  padding: 0.75rem 1rem;
  resize: vertical;
  font-family: var(--font-sans);
  outline: none;
  transition: border-color 0.2s;
}
.topic-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-dim);
}

.input-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 1rem;
}

.search-select {
  flex: 0 0 auto;
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-primary);
  padding: 0.5rem 0.75rem;
  font-size: 0.9rem;
  outline: none;
}

.btn-primary {
  flex: 1;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--radius);
  padding: 0.6rem 1.25rem;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}
.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
}
.btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

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
.btn-ghost:hover:not(:disabled) {
  color: var(--text-primary);
  border-color: var(--border-light);
}
.btn-ghost:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-sm {
  padding: 0.35rem 0.7rem;
  font-size: 0.8rem;
}

.link-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  margin-top: 1.5rem;
  font-size: 0.9rem;
}
.link-btn:hover {
  color: var(--accent);
}

.error-msg {
  color: var(--error);
  margin-top: 0.75rem;
  font-size: 0.9rem;
}

/* ── Research View ─────────────────────────────────────────────────────── */
.research-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.research-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1.25rem;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  gap: 1rem;
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex: 1;
  min-width: 0;
}
.header-topic {
  font-size: 1rem;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 300px;
}
.progress-bar-wrap {
  width: 120px;
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.4s ease;
}
.progress-label {
  font-size: 0.8rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
}
.header-actions {
  display: flex;
  gap: 0.5rem;
  flex-shrink: 0;
}

/* ── Body Layout ───────────────────────────────────────────────────────── */
.research-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.left-panel {
  width: 320px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.right-panel {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem;
  background: var(--bg-card);
}

.panel-section {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.panel-section:first-child {
  max-height: 40%;
}
.panel-section:last-child {
  flex: 1;
  border-top: 1px solid var(--border);
}

.section-title {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  padding: 0.75rem 1rem 0.5rem;
}

/* ── Activity Log ──────────────────────────────────────────────────────── */
.activity-log {
  overflow-y: auto;
  padding: 0 0.75rem 0.75rem;
  font-size: 0.8rem;
  font-family: var(--font-mono);
}
.log-entry {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.3rem 0.4rem;
  border-radius: 4px;
  line-height: 1.4;
}
.log-icon {
  flex-shrink: 0;
  width: 1.2em;
  text-align: center;
}
.log-msg {
  flex: 1;
  color: var(--text-secondary);
  word-break: break-all;
}
.log-time {
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 0.7rem;
}
.log-search .log-msg {
  color: var(--warning);
}
.log-evaluate .log-msg {
  color: var(--accent);
}
.log-error .log-msg {
  color: var(--error);
}
.log-report .log-msg {
  color: var(--success);
}

.log-active {
  animation: pulse-fade 1.5s infinite;
}

.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  display: inline-block;
  margin-top: 3px;
  animation: pulse-scale 1s infinite;
}

@keyframes pulse-scale {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.4);
    opacity: 0.6;
  }
}
@keyframes pulse-fade {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

/* ── Task List ─────────────────────────────────────────────────────────── */
.task-list {
  overflow-y: auto;
  padding: 0.5rem 0.75rem;
}
.task-card {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  padding: 0.6rem 0.75rem;
  border-radius: var(--radius);
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 0.25rem;
}
.task-card:hover {
  background: var(--bg-tertiary);
}
.task-card.active {
  background: var(--accent-dim);
  border-left: 3px solid var(--accent);
}

.task-icon {
  font-size: 0.85rem;
  margin-top: 2px;
  flex-shrink: 0;
  width: 1.2em;
  text-align: center;
}
.icon-completed {
  color: var(--success);
}
.icon-summarized {
  color: var(--warning);
}
.icon-in_progress {
  color: var(--accent);
  animation: pulse-scale 1s infinite;
}
.icon-failed {
  color: var(--error);
}
.icon-pending {
  color: var(--text-muted);
}

.task-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.task-title {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-primary);
}
.task-intent {
  font-size: 0.75rem;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Detail Section ────────────────────────────────────────────────────── */
.detail-section {
  margin-bottom: 2rem;
}
.detail-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.detail-header h3 {
  font-size: 1.15rem;
}
.badge {
  font-size: 0.7rem;
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  font-weight: 500;
  text-transform: uppercase;
}
.badge-completed {
  background: var(--success-dim);
  color: var(--success);
}
.badge-summarized {
  background: var(--warning-dim);
  color: var(--warning);
}
.badge-in_progress {
  background: var(--accent-dim);
  color: var(--accent);
}
.badge-failed {
  background: var(--error-dim);
  color: var(--error);
}
.badge-pending {
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.detail-meta {
  font-size: 0.85rem;
  color: var(--text-secondary);
  line-height: 1.7;
  margin-bottom: 1rem;
}

/* ── Sources ───────────────────────────────────────────────────────────── */
.sources-block {
  margin-bottom: 1.25rem;
}
.sources-block h4 {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.source-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}
.source-chip {
  display: inline-block;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.25rem 0.6rem;
  font-size: 0.75rem;
  color: var(--accent);
  max-width: 260px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: border-color 0.2s;
}
.source-chip:hover {
  border-color: var(--accent);
  text-decoration: none;
}
.source-chip.no-link {
  color: var(--text-secondary);
  cursor: default;
}
.source-chip.no-link:hover {
  border-color: var(--border);
}

/* ── Summary ───────────────────────────────────────────────────────────── */
.summary-block h4 {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-bottom: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.summary-placeholder {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  color: var(--text-muted);
  font-size: 0.9rem;
  padding: 1rem 0;
}

.typing-indicator {
  display: flex;
  gap: 3px;
}
.typing-indicator span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent);
  animation: typing-bounce 1.2s infinite;
}
.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}
.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing-bounce {
  0%,
  60%,
  100% {
    transform: translateY(0);
    opacity: 0.4;
  }
  30% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

/* ── Report ────────────────────────────────────────────────────────────── */
.report-section {
  border-top: 1px solid var(--border);
  padding-top: 1.5rem;
}
.report-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}
.report-header h3 {
  font-size: 1.15rem;
}

.report-body {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 2rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  overflow-wrap: break-word;
  word-wrap: break-word;
}

/* ── Empty state ───────────────────────────────────────────────────────── */
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--text-muted);
}

.btn-trace {
  color: var(--accent) !important;
  border-color: var(--accent) !important;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}
.btn-trace:hover {
  background: var(--accent-dim);
}

.error-banner {
  background: var(--error-dim);
  color: var(--error);
  padding: 0.75rem 1rem;
  border-radius: var(--radius);
  margin-bottom: 1rem;
  font-size: 0.9rem;
}
</style>
