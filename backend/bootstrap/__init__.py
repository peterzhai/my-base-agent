"""启动模块公开入口：延迟导入种子逻辑，读取配置不会提前加载数据库和安全服务。"""

from importlib import import_module

__all__ = ["bootstrap", "seed_demo"]


def __getattr__(name):
    """只在显式请求初始化函数时加载，避免 settings→seeding→security 的循环依赖。"""
    if name not in __all__:
        raise AttributeError(name)
    return getattr(import_module("backend.bootstrap.seeding"), name)
