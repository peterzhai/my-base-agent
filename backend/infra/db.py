"""兼容旧导入 backend.infra.db；实现已迁移到 backend.infrastructure.persistence.database，新代码请直接使用新路径。"""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("backend.infrastructure.persistence.database")
