export interface TaskItem {
  id: number;
  title: string;
  intent: string;
  query: string;
}

export interface SourceItem {
  title: string;
  url: string;
  content: string;
}

export interface TaskView {
  id: number;
  title: string;
  intent: string;
  query: string;
  status: "pending" | "in_progress" | "summarized" | "completed" | "failed";
  summary: string;
  sources: SourceItem[];
}

export interface ActivityLog {
  id: number;
  message: string;
  type: "info" | "search" | "summarize" | "evaluate" | "report" | "error";
  taskId?: number;
  time: string;
}

export type SSEEvent =
  | { type: "status"; message: string; task_id?: number }
  | { type: "todo_list"; tasks: TaskItem[] }
  | { type: "task_status"; task_id: number; status: string; title: string }
  | { type: "sources"; task_id: number; sources: SourceItem[] }
  | { type: "task_summary_chunk"; task_id: number; content: string }
  | { type: "task_summary_clear"; task_id: number }
  | { type: "report_chunk"; content: string }
  | { type: "final_report"; report: string; report_id: string | null }
  | { type: "error"; detail: string }
  | { type: "done" };

export interface ReportSummary {
  id: string;
  topic: string;
  created_at: string;
}

export interface ReportDetail {
  id: string;
  topic: string;
  report_markdown: string;
  tasks: TaskView[];
  created_at: string;
}
