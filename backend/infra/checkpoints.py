"""兼容旧导入 backend.infra.checkpoints；实现已迁移到 backend.infrastructure.persistence.checkpoints，新代码请直接使用新路径。"""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("backend.infrastructure.persistence.checkpoints")
