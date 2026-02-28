import operator
from typing import Annotated, TypedDict


class ResearchState(TypedDict):
    """Main graph state for the research workflow."""
    topic: str
    search_api: str
    tasks: list[dict]
    completed_tasks: Annotated[list[dict], operator.add]
    report: str


class TaskResult(TypedDict):
    """Result of a single research task execution."""
    task_id: int
    title: str
    intent: str
    query: str
    summary: str
    sources: list[dict]
    status: str
