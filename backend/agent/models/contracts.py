"""模块公开契约与值对象；不包含 HTTP、数据库或工厂具体业务。"""

from typing import AsyncIterator, Protocol


class ModelGateway(Protocol):
    """模型端口：调用方依赖能力协议，不依赖某家模型服务的 HTTP 格式。"""

    async def complete(self, messages: list[dict], *, structured: bool = False) -> str:
        """返回完整文本；structured 表示请求 JSON，业务方仍须校验模式。"""
        ...

    def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """逐段产生文本；必须遵守取消和错误传播契约。"""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """按输入顺序返回向量，不能在替代实现中改变数量和排序。"""
        ...
