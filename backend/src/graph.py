import asyncio
import json
import re
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from loguru import logger

from .config import get_config
from .models import ResearchState
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




# ── Nodes ────────────────────────────────────────────────────────────────────


async def plan_node(state: ResearchState, config: RunnableConfig) -> dict:
    """Decompose topic into research sub-tasks."""
    queue = config["configurable"]["event_queue"]
    topic = state["topic"]

    logger.info(f"[Node: plan] 正在执行 Planner Agent | 主题: {topic!r}")
    await queue.put({"type": "status", "message": "正在规划研究任务..."})

    llm = get_llm()
    user_msg = f"研究主题：{topic}\n\n请为这个主题规划3-5个研究子任务。"

    response = await llm.ainvoke([
        _system_msg(PLANNER_PROMPT),
        HumanMessage(content=user_msg),
    ])

    tasks = _parse_tasks(response.content)
    logger.info(f"[Node: plan] Planner 完成 → 生成 {len(tasks)} 个子任务")
    for t in tasks:
        logger.info(f"  #{t['id']} {t['title']} (query: {t['query']!r})")

    await queue.put({"type": "todo_list", "tasks": tasks})
    return {"tasks": tasks}


async def execute_all_tasks(state: ResearchState, config: RunnableConfig) -> dict:
    """Execute ALL research tasks in parallel using asyncio.gather."""
    queue = config["configurable"]["event_queue"]
    topic = state["topic"]
    search_api = state.get("search_api", "tavily")

    logger.info(f"[Node: execute_all_tasks] 并行启动 {len(state['tasks'])} 个子任务 | search_api={search_api}")

    async def _run_single_task(task: dict) -> dict:
        task_id = task["id"]
        tag = f"[Task #{task_id}]"
        try:
            logger.info(f"{tag} 开始执行 | {task['title']!r}")

            # ── in_progress ──────────────────────────────────────────
            await queue.put({
                "type": "task_status",
                "task_id": task_id,
                "status": "in_progress",
                "title": task["title"],
            })

            # ── Search ───────────────────────────────────────────────
            await queue.put({
                "type": "status",
                "message": f"搜索中：{task['query']}",
                "task_id": task_id,
            })
            search_results = await perform_search(task["query"], search_api)
            logger.info(f"{tag} 搜索完成 → {len(search_results)} 条结果")

            await queue.put({
                "type": "sources",
                "task_id": task_id,
                "sources": search_results,
            })

            # ── Summarise (streaming) ────────────────────────────────
            await queue.put({
                "type": "status",
                "message": f"正在总结：{task['title']}",
                "task_id": task_id,
            })

            llm = get_llm()
            context = format_search_context(search_results)
            summary_prompt = (
                f"研究主题：{topic}\n"
                f"任务：{task['title']}\n"
                f"意图：{task['intent']}\n"
                f"搜索查询：{task['query']}\n\n"
                f"搜索结果：\n{context}"
            )

            logger.info(f"{tag} 正在执行 Summarizer Agent | {task['title']!r}")

            summary = ""
            async for chunk in llm.astream([
                _system_msg(SUMMARIZER_PROMPT),
                HumanMessage(content=summary_prompt),
            ]):
                if chunk.content:
                    summary += chunk.content
                    await queue.put({
                        "type": "task_summary_chunk",
                        "task_id": task_id,
                        "content": chunk.content,
                    })

            logger.info(f"{tag} Summarizer 完成 → {len(summary)} chars")

            # ── Self-correction ──────────────────────────────────────
            cfg = get_config()
            if cfg.max_retry_count > 0:
                await queue.put({
                    "type": "status",
                    "message": f"评估质量：{task['title']}",
                    "task_id": task_id,
                })

                logger.info(f"{tag} 正在执行 Evaluator Agent | 评估总结质量")

                eval_user_msg = (
                    f"任务意图：{task['intent']}\n\n"
                    f"当前总结：\n{summary}\n\n"
                    f"请评估这个总结的质量。"
                )

                eval_response = await llm.ainvoke([
                    _system_msg(EVALUATOR_PROMPT),
                    HumanMessage(content=eval_user_msg),
                ])

                needs_retry, refined_query = _parse_evaluation(eval_response.content)
                logger.info(f"{tag} Evaluator 完成 → needs_retry={needs_retry}" + (f", refined_query={refined_query!r}" if refined_query else ""))

                if needs_retry and refined_query:
                    await queue.put({
                        "type": "status",
                        "message": f"自纠错：补充搜索 — {refined_query}",
                        "task_id": task_id,
                    })

                    logger.info(f"{tag} 补充搜索 | query={refined_query!r}")
                    new_results = await perform_search(refined_query, search_api)
                    logger.info(f"{tag} 补充搜索完成 → {len(new_results)} 条结果")
                    search_results.extend(new_results)
                    context = format_search_context(search_results)

                    await queue.put({
                        "type": "task_summary_clear",
                        "task_id": task_id,
                    })

                    logger.info(f"{tag} 正在执行 Summarizer Agent (重试) | {task['title']!r}")

                    summary = ""
                    retry_prompt = (
                        f"研究主题：{topic}\n"
                        f"任务：{task['title']}\n"
                        f"意图：{task['intent']}\n"
                        f"搜索查询：{task['query']}\n"
                        f"补充查询：{refined_query}\n\n"
                        f"搜索结果：\n{context}"
                    )

                    async for chunk in llm.astream([
                        _system_msg(SUMMARIZER_PROMPT),
                        HumanMessage(content=retry_prompt),
                    ]):
                        if chunk.content:
                            summary += chunk.content
                            await queue.put({
                                "type": "task_summary_chunk",
                                "task_id": task_id,
                                "content": chunk.content,
                            })

                    logger.info(f"{tag} Summarizer (重试) 完成 → {len(summary)} chars")

            # ── Summarized ────────────────────────────────────────────
            await queue.put({
                "type": "task_status",
                "task_id": task_id,
                "status": "summarized",
                "title": task["title"],
            })

            logger.info(f"{tag} 任务完成 → summary={len(summary)} chars, sources={len(search_results)}")

            return {
                "task_id": task_id,
                "title": task["title"],
                "intent": task["intent"],
                "query": task["query"],
                "summary": summary,
                "sources": search_results,
                "status": "summarized",
            }

        except Exception as e:
            logger.error(f"{tag} 执行失败: {e}")
            await queue.put({
                "type": "task_status",
                "task_id": task_id,
                "status": "failed",
                "title": task.get("title", ""),
            })
            return {
                "task_id": task_id,
                "title": task.get("title", ""),
                "intent": task.get("intent", ""),
                "query": task.get("query", ""),
                "summary": f"任务执行失败：{e}",
                "sources": [],
                "status": "failed",
            }

    # Run every task concurrently; gather waits for ALL to finish
    results = await asyncio.gather(
        *[_run_single_task(t) for t in state["tasks"]]
    )

    logger.info(f"[Node: execute_all_tasks] 全部 {len(results)} 个子任务完成 | " + ", ".join(f"#{r['task_id']}={r['status']}" for r in results))

    return {"completed_tasks": list(results)}


async def report_node(state: ResearchState, config: RunnableConfig) -> dict:
    """Synthesise all task results into a final report."""
    queue = config["configurable"]["event_queue"]

    logger.info(f"[Node: report] 正在执行 Reporter Agent | 生成最终报告")
    await queue.put({"type": "status", "message": "正在生成研究报告..."})

    llm = get_llm()

    # ── Step 1: Build global deduplicated & numbered source list ─────
    global_sources, task_source_maps = _build_source_maps(state["completed_tasks"])

    raw_count = sum(len(t.get("sources", [])) for t in state["completed_tasks"])
    logger.info(f"[Node: report] 来源去重: {raw_count} → {len(global_sources)} 条")

    # Build the numbered reference block for the LLM
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

    report = ""
    async for chunk in llm.astream([
        _system_msg(REPORTER_PROMPT),
        HumanMessage(content=user_msg),
    ]):
        if chunk.content:
            report += chunk.content
            await queue.put({"type": "report_chunk", "content": chunk.content})

    # Now that the report is done, mark all tasks as truly "completed"
    for t in state["completed_tasks"]:
        await queue.put({
            "type": "task_status",
            "task_id": t["task_id"],
            "status": "completed",
            "title": t["title"],
        })

    logger.info(f"[Node: report] Reporter 完成 → {len(report)} chars, 全部任务标记为 completed")

    return {"report": report}


# ── Graph builder ────────────────────────────────────────────────────────────


def build_graph():
    """Construct and compile the research LangGraph.

    Flow: START → plan → execute_all_tasks → report → END
    Parallelism is handled inside execute_all_tasks via asyncio.gather,
    which guarantees report only starts after every task finishes.
    """
    builder = StateGraph(ResearchState)

    builder.add_node("plan", plan_node)
    builder.add_node("execute_all_tasks", execute_all_tasks)
    builder.add_node("report", report_node)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "execute_all_tasks")
    builder.add_edge("execute_all_tasks", "report")
    builder.add_edge("report", END)

    return builder.compile()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_source_maps(
    completed_tasks: list[dict],
) -> tuple[list[dict], dict[int, dict[int, int]]]:
    """Build deduplicated global source list and per-task citation mappings.

    Returns (global_sources, task_source_maps) where:
      - global_sources: [{title, url}, ...] with 1-based indexing
      - task_source_maps: {task_id: {local_idx: global_idx}}
    """
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
            key = url or title  # prefer URL for dedup
            if key not in seen_keys:
                global_sources.append({"title": title or url, "url": url})
                seen_keys[key] = len(global_sources)  # 1-based
            local_map[local_idx] = seen_keys[key]
        task_source_maps[tid] = local_map

    return global_sources, task_source_maps


def _remap_citations(summary: str, local_map: dict[int, int]) -> str:
    """Replace local [N] references with global [M] references."""
    if not local_map:
        return summary

    def _replace(m):
        local_id = int(m.group(1))
        global_id = local_map.get(local_id)
        if global_id is not None:
            return f"[{global_id}]"
        return m.group(0)

    return re.sub(r'\[(\d+)\]', _replace, summary)


def _parse_tasks(content: str) -> list[dict]:
    """Extract planned tasks from LLM JSON response."""
    try:
        match = re.search(r"\{.*\"tasks\".*\}", content, re.DOTALL)
        if match:
            data = json.loads(match.group())
            raw_tasks = data.get("tasks", [])
        else:
            arr_match = re.search(r"\[.*\]", content, re.DOTALL)
            if arr_match:
                raw_tasks = json.loads(arr_match.group())
            else:
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
        logger.warning(f"[Plan] Failed to parse tasks: {e}, creating fallback")
        return [
            {
                "id": 1,
                "title": "基础背景研究",
                "intent": "了解主题的基本背景和核心概念",
                "query": content[:100] if content else "基础研究",
            }
        ]


def _parse_evaluation(content: str) -> tuple[bool, str | None]:
    """Extract evaluation result from LLM JSON response."""
    try:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return data.get("needs_retry", False), data.get("refined_query") or None
    except Exception:
        pass
    return False, None
