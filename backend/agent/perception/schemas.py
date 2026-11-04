"""模块公开契约与值对象；不包含 HTTP、数据库或工厂具体业务。"""

from pydantic import BaseModel


class Route(BaseModel):
    """感知结果：选择能力、补全问题、主题与依赖顺序，不承载原始 SQL。"""

    route: str  # knowledge / data / mixed / clarify
    question: str
    topic_id: str | None = None
    sequential: bool = False
    clarification: str = ""
