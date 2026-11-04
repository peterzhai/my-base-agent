"""模块公开契约与值对象；不包含 HTTP、数据库或工厂具体业务。"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Principal:
    """不可变身份值对象：将身份与数据库实体分离，业务代码不能修改调用者权限。"""

    user_id: str
    department: str
    roles: tuple[str, ...]
    permission_version: int = 1

    @property
    def admin(self) -> bool:
        """只判断身份中的管理员角色；资源启用状态和数据范围仍需单独校验。"""
        return "admin" in self.roles


class ExecutionPolicy(Protocol):
    """授权策略扩展端口；当前应用仍通过安全服务函数实现授权。"""

    def authorize(self, principal: Principal, resource: str, action: str) -> bool:
        """判定主体是否可对资源执行动作；决策不能由模型绕过。"""
        ...
