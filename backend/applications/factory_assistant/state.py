"""工厂问答图状态；这是领域载荷，不假装是所有 Agent 通用状态。"""

from typing import TypedDict


class State(TypedDict, total=False):
    """一次工作流运行的状态载荷，不是跨用户共享的长期记忆。"""

    question: str
    route: dict
    evidence: list[dict]
    tables: list[dict]
    errors: list[str]
    clarification: str
    answer: str
