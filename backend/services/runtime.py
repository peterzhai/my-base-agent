"""兼容旧导入 backend.services.runtime；实现已迁移到 backend.applications.factory_assistant.runtime，新代码请直接使用新路径。"""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("backend.applications.factory_assistant.runtime")
