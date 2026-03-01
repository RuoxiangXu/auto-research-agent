import json
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from loguru import logger

from .config import get_config
from .models import ResearchState, TaskState
from .prompts import EVALUATOR_PROMPT, PLANNER_PROMPT, REPORTER_PROMPT, SUMMARIZER_PROMPT
from .search import format_search_context, perform_search


def get_llm() -> ChatOpenAI:
    cfg = get_config()
    return ChatOpenAI(
        model=cfg.llm_model_id,
        api_key=cfg.llm_api_key,
        base_url=cfg.llm_base_url or None,
        temperature=0.0,
    )


def _system_msg(prompt: str) -> SystemMessage:
    """Build a SystemMessage with the current date prepended."""
    today = date.today().strftime("%Y-%m-%d")
    return SystemMessage(content=f"当前日期：{today}\n\n{prompt}")


# ══════════════════════════════════════════════════════════════════════════════
# Task subgraph nodes: SearchAgent → SummarizerAgent → EvaluatorAgent
# ══════════════════════════════════════════════════════════════════════════════


async def search_node(state: TaskState, config: RunnableConfig) -> dict:
    """SearchAgent: perform web search for the current task."""
    queue = config["configurable"]["event_queue"]
    task = state["task"]
    task_id = task["id"]
    search_api = state["search_api"]
    is_retry = state["retry_count"] > 0

    query = state["refined_query"] if is_retry else task["query"]
    label = "补充搜索" if is_retry else "搜索"

    await queue.put({
        "type": "status",
        "message": f"SearchAgent: {label} — {query}",
        "task_id": task_id,
    })

    search_results, actual_provider = await perform_search(query, search_api)
    logger.info(f"[Task #{task_id}] SearchAgent {label}完成 → {len(search_results)} 条结果 via {actual_provider}")

    if actual_provider != search_api:
        await queue.put({
            "type": "status",
            "message": f"SearchAgent: 回退 {search_api} → {actual_provider}",
            "task_id": task_id,
        })

    # On retry, extend existing results; on first run, use new results directly
    all_results = state["search_results"] + search_results if is_retry else search_results

    await queue.put({
        "type": "sources",
        "task_id": task_id,
        "sources": all_results,
    })

    return {"search_results": all_results}


async def summarize_node(state: TaskState, config: RunnableConfig) -> dict:
    """SummarizerAgent: generate a streaming summary from search results."""
    queue = config["configurable"]["event_queue"]
    task = state["task"]
    task_id = task["id"]
    is_retry = state["retry_count"] > 0

    # Clear previous summary on retry
    if is_retry:
        await queue.put({"type": "task_summary_clear", "task_id": task_id})

    label = "重新总结" if is_retry else "总结"
    await queue.put({
        "type": "status",
        "message": f"SummarizerAgent: {label} — {task['title']}",
        "task_id": task_id,
    })

    llm = get_llm()
    context = format_search_context(state["search_results"])
    prompt_parts = (
        f"研究主题：{state['topic']}\n"
        f"任务：{task['title']}\n"
        f"意图：{task['intent']}\n"
        f"搜索查询：{task['query']}\n"
    )
    if is_retry and state["refined_query"]:
        prompt_parts += f"补充查询：{state['refined_query']}\n"
    prompt_parts += f"\n搜索结果：\n{context}"

    logger.info(f"[Task #{task_id}] SummarizerAgent {'(retry)' if is_retry else ''} | {task['title']!r}")

    summary = ""
    async for chunk in llm.astream([
        _system_msg(SUMMARIZER_PROMPT),
        HumanMessage(content=prompt_parts),
    ]):
        if chunk.content:
            summary += chunk.content
            await queue.put({
                "type": "task_summary_chunk",
                "task_id": task_id,
                "content": chunk.content,
            })

    logger.info(f"[Task #{task_id}] SummarizerAgent 完成 → {len(summary)} chars")

    return {"summary": summary}


async def evaluate_node(state: TaskState, config: RunnableConfig) -> dict:
    """EvaluatorAgent: assess summary quality and decide whether to retry."""
    queue = config["configurable"]["event_queue"]
    task = state["task"]
    task_id = task["id"]

    await queue.put({
        "type": "status",
        "message": f"EvaluatorAgent: 评估质量 — {task['title']}",
        "task_id": task_id,
    })

    cfg = get_config()
    logger.info(f"[Task #{task_id}] EvaluatorAgent (round {state['retry_count'] + 1}/{cfg.max_retry_count})")

    llm = get_llm()
    eval_user_msg = (
        f"任务意图：{task['intent']}\n\n"
        f"当前总结：\n{state['summary']}\n\n"
        f"请评估这个总结的质量。"
    )

    eval_response = await llm.ainvoke([
        _system_msg(EVALUATOR_PROMPT),
        HumanMessage(content=eval_user_msg),
    ])

    needs_retry, refined_query = _parse_evaluation(eval_response.content)
    logger.info(f"[Task #{task_id}] EvaluatorAgent → needs_retry={needs_retry}" + (f", refined_query={refined_query!r}" if refined_query else ""))

    # Decide: retry if quality is low AND retries remain AND we have a refined query
    should_retry = (
        needs_retry
        and refined_query
        and state["retry_count"] < cfg.max_retry_count
    )

    if should_retry:
        await queue.put({
            "type": "status",
            "message": f"EvaluatorAgent: 需要补充搜索 — {refined_query}",
            "task_id": task_id,
        })
        return {
            "refined_query": refined_query,
            "retry_count": state["retry_count"] + 1,
        }

    # Quality is acceptable (or max retries reached) — mark task as summarized
    await queue.put({
        "type": "task_status",
        "task_id": task_id,
        "status": "summarized",
        "title": task["title"],
    })
    logger.info(f"[Task #{task_id}] 任务完成 → summary={len(state['summary'])} chars, sources={len(state['search_results'])}")

    # Clear refined_query so should_retry routes to END
    return {"refined_query": ""}


def should_retry(state: TaskState) -> str:
    """Routing function: retry search or finish the task.

    When evaluate_node decides to retry, it sets refined_query to a non-empty
    string and increments retry_count. When it accepts the summary, it clears
    refined_query to an empty string, so this function routes to END.
    """
    if state.get("refined_query"):
        return "SearchAgent"
    return END


def _build_task_graph() -> StateGraph:
    """Build the task execution subgraph.

    Flow: SearchAgent → SummarizerAgent → EvaluatorAgent → [retry? → SearchAgent : END]
    """
    builder = StateGraph(TaskState)

    builder.add_node("SearchAgent", search_node)
    builder.add_node("SummarizerAgent", summarize_node)
    builder.add_node("EvaluatorAgent", evaluate_node)

    builder.add_edge(START, "SearchAgent")
    builder.add_edge("SearchAgent", "SummarizerAgent")
    builder.add_edge("SummarizerAgent", "EvaluatorAgent")
    builder.add_conditional_edges("EvaluatorAgent", should_retry, {
        "SearchAgent": "SearchAgent",
        END: END,
    })

    return builder.compile()


# Compile once and reuse
_task_graph = _build_task_graph()


# ══════════════════════════════════════════════════════════════════════════════
# Main graph nodes: PlannerAgent → [TaskSubgraph × N] → ReporterAgent
# ══════════════════════════════════════════════════════════════════════════════


async def plan_node(state: ResearchState, config: RunnableConfig) -> dict:
    """PlannerAgent: decompose topic into research sub-tasks."""
    queue = config["configurable"]["event_queue"]
    topic = state["topic"]

    logger.info(f"[PlannerAgent] 主题: {topic!r}")
    await queue.put({"type": "status", "message": "PlannerAgent: 正在规划研究任务..."})

    llm = get_llm()
    user_msg = f"研究主题：{topic}\n\n请为这个主题规划3-5个研究子任务。"

    response = await llm.ainvoke([
        _system_msg(PLANNER_PROMPT),
        HumanMessage(content=user_msg),
    ])

    tasks = _parse_tasks(response.content, topic)
    logger.info(f"[PlannerAgent] 完成 → 生成 {len(tasks)} 个子任务")
    for t in tasks:
        logger.info(f"  #{t['id']} {t['title']} (query: {t['query']!r})")

    await queue.put({"type": "todo_list", "tasks": tasks})
    return {"tasks": tasks}


def route_to_tasks(state: ResearchState) -> list[Send]:
    """Fan-out: create a parallel TaskSubgraph invocation for each planned task."""
    return [
        Send("TaskSubgraph", {
            "task": task,
            "topic": state["topic"],
            "search_api": state.get("search_api", "duckduckgo"),
            "search_results": [],
            "summary": "",
            "retry_count": 0,
            "refined_query": "",
        })
        for task in state["tasks"]
    ]


async def task_subgraph(state: dict, config: RunnableConfig) -> dict:
    """TaskSubgraph: invoke the task pipeline with error handling.

    Receives per-task state from Send(), runs the SearchAgent → SummarizerAgent
    → EvaluatorAgent pipeline, and returns the result for accumulation.
    """
    queue = config["configurable"]["event_queue"]
    task = state["task"]
    task_id = task["id"]

    try:
        logger.info(f"[Task #{task_id}] 开始执行 | {task['title']!r}")
        await queue.put({
            "type": "task_status",
            "task_id": task_id,
            "status": "in_progress",
            "title": task["title"],
        })

        # Run the task subgraph
        result = await _task_graph.ainvoke(state, config=config)

        return {
            "completed_tasks": [{
                "task_id": task_id,
                "title": task["title"],
                "intent": task["intent"],
                "query": task["query"],
                "summary": result["summary"],
                "sources": result["search_results"],
                "status": "summarized",
            }],
        }

    except Exception as e:
        logger.error(f"[Task #{task_id}] 执行失败: {e}")
        await queue.put({
            "type": "task_status",
            "task_id": task_id,
            "status": "failed",
            "title": task.get("title", ""),
        })
        return {
            "completed_tasks": [{
                "task_id": task_id,
                "title": task.get("title", ""),
                "intent": task.get("intent", ""),
                "query": task.get("query", ""),
                "summary": f"任务执行失败：{e}",
                "sources": [],
                "status": "failed",
            }],
        }


async def report_node(state: ResearchState, config: RunnableConfig) -> dict:
    """ReporterAgent: synthesise all task results into a final report."""
    queue = config["configurable"]["event_queue"]

    logger.info(f"[ReporterAgent] 生成最终报告")
    await queue.put({"type": "status", "message": "ReporterAgent: 正在生成研究报告..."})

    llm = get_llm()

    # ── Step 1: Build global deduplicated & numbered source list ─────
    global_sources, task_source_maps = _build_source_maps(state["completed_tasks"])

    raw_count = sum(len(t.get("sources", [])) for t in state["completed_tasks"])
    logger.info(f"[ReporterAgent] 来源去重: {raw_count} → {len(global_sources)} 条")

    source_ref_lines = []
    for i, src in enumerate(global_sources, 1):
        if src["url"]:
            source_ref_lines.append(f"[{i}] {src['title']} — {src['url']}")
        else:
            source_ref_lines.append(f"[{i}] {src['title']}")
    source_ref_block = "\n".join(source_ref_lines) if source_ref_lines else "（无来源）"

    # ── Step 2: Build per-task context with remapped summaries ──────
    tasks_context = ""
    for t in state["completed_tasks"]:
        tid = t["task_id"]
        remapped_summary = _remap_citations(t["summary"], task_source_maps.get(tid, {}))

        tasks_context += (
            f"### 任务 {tid}: {t['title']}\n"
            f"- 任务意图：{t['intent']}\n"
            f"- 检索查询：{t['query']}\n"
            f"- 执行状态：{t['status']}\n"
            f"- 任务总结：\n{remapped_summary}\n\n---\n\n"
        )

    user_msg = (
        f"研究主题：{state['topic']}\n\n"
        f"以下是各子任务的研究结果：\n\n{tasks_context}\n\n"
        f"全部参考来源（统一编号）：\n{source_ref_block}\n\n"
        f"请基于以上内容生成一份完整的研究报告。在正文中使用数字编号引用来源，如[1][2]。"
        f"在报告末尾的参考来源章节中，列出上述编号对应的来源。"
    )

    messages = [_system_msg(REPORTER_PROMPT), HumanMessage(content=user_msg)]

    report = ""
    async for chunk in llm.astream(messages):
        if chunk.content:
            report += chunk.content
            await queue.put({"type": "report_chunk", "content": chunk.content})

    # Fallback: if streaming returned empty (known issue after burst concurrent
    # LLM calls), retry with a non-streaming ainvoke call.
    if not report:
        logger.warning("[ReporterAgent] astream returned empty, falling back to ainvoke")
        response = await llm.ainvoke(messages)
        report = response.content or ""
        if report:
            await queue.put({"type": "report_chunk", "content": report})

    # Mark all tasks as truly "completed"
    for t in state["completed_tasks"]:
        await queue.put({
            "type": "task_status",
            "task_id": t["task_id"],
            "status": "completed",
            "title": t["title"],
        })

    logger.info(f"[ReporterAgent] 完成 → {len(report)} chars")

    return {"report": report}


# ══════════════════════════════════════════════════════════════════════════════
# Graph builder
# ══════════════════════════════════════════════════════════════════════════════


def build_graph():
    """Construct and compile the research LangGraph.

    Main graph flow:
        START → PlannerAgent → [TaskSubgraph × N via Send] → ReporterAgent → END

    Each TaskSubgraph runs an inner pipeline:
        SearchAgent → SummarizerAgent → EvaluatorAgent → [retry? → SearchAgent : END]

    Parallelism is handled natively by LangGraph's Send() API for fan-out.
    The operator.add reducer on completed_tasks handles fan-in accumulation.
    """
    builder = StateGraph(ResearchState)

    builder.add_node("PlannerAgent", plan_node)
    builder.add_node("TaskSubgraph", task_subgraph)
    builder.add_node("ReporterAgent", report_node)

    builder.add_edge(START, "PlannerAgent")
    builder.add_conditional_edges("PlannerAgent", route_to_tasks, ["TaskSubgraph"])
    builder.add_edge("TaskSubgraph", "ReporterAgent")
    builder.add_edge("ReporterAgent", END)

    return builder.compile()


_main_graph = None


def get_graph():
    """Return a cached compiled research graph (compile once, reuse across requests)."""
    global _main_graph
    if _main_graph is None:
        _main_graph = build_graph()
    return _main_graph


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════


def _build_source_maps(
    completed_tasks: list[dict],
) -> tuple[list[dict], dict[int, dict[int, int]]]:
    """Build deduplicated global source list and per-task citation mappings."""
    global_sources: list[dict] = []
    seen_keys: dict[str, int] = {}
    task_source_maps: dict[int, dict[int, int]] = {}

    for t in completed_tasks:
        tid = t["task_id"]
        local_map: dict[int, int] = {}
        for local_idx, s in enumerate(t.get("sources", []), 1):
            title = s.get("title", "").strip()
            url = s.get("url", "").strip()
            if not title and not url:
                continue
            key = url or title
            if key not in seen_keys:
                global_sources.append({"title": title or url, "url": url})
                seen_keys[key] = len(global_sources)
            local_map[local_idx] = seen_keys[key]
        task_source_maps[tid] = local_map

    return global_sources, task_source_maps


def _remap_citations(summary: str, local_map: dict[int, int]) -> str:
    """Replace local [N] references with global [M] references."""
    if not local_map:
        return summary

    max_local = max(local_map.keys())

    def _replace(m):
        local_id = int(m.group(1))
        if local_id > max_local:
            return m.group(0)
        global_id = local_map.get(local_id)
        if global_id is not None:
            return f"[{global_id}]"
        return m.group(0)

    return re.sub(r'\[(\d+)\]', _replace, summary)


def _extract_json(content: str, open_char: str = "{", close_char: str = "}") -> str | None:
    """Extract the first balanced JSON object/array from content."""
    start = content.find(open_char)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(content)):
        c = content[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == open_char:
            depth += 1
        elif c == close_char:
            depth -= 1
            if depth == 0:
                return content[start : i + 1]
    return None


def _parse_tasks(content: str, topic: str = "") -> list[dict]:
    """Extract planned tasks from LLM JSON response."""
    try:
        raw_tasks = None

        obj_str = _extract_json(content, "{", "}")
        if obj_str:
            data = json.loads(obj_str)
            if isinstance(data, dict) and "tasks" in data:
                raw_tasks = data["tasks"]

        if raw_tasks is None:
            arr_str = _extract_json(content, "[", "]")
            if arr_str:
                raw_tasks = json.loads(arr_str)

        if raw_tasks is None:
            raise ValueError("no json found")

        return [
            {
                "id": i + 1,
                "title": t.get("title", f"任务 {i + 1}"),
                "intent": t.get("intent", ""),
                "query": t.get("query", t.get("title", "")),
            }
            for i, t in enumerate(raw_tasks)
        ]
    except Exception as e:
        logger.warning(f"[PlannerAgent] Failed to parse tasks: {e}, creating fallback")
        return [
            {
                "id": 1,
                "title": "基础背景研究",
                "intent": "了解主题的基本背景和核心概念",
                "query": topic if topic else "基础研究",
            }
        ]


def _parse_evaluation(content: str) -> tuple[bool, str | None]:
    """Extract evaluation result from LLM JSON response."""
    try:
        obj_str = _extract_json(content, "{", "}")
        if obj_str:
            data = json.loads(obj_str)
            return data.get("needs_retry", False), data.get("refined_query") or None
    except Exception:
        pass
    return False, None
