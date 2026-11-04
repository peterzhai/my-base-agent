"""兼容旧导入 backend.services.jobs；实现已迁移到 backend.infrastructure.jobs.worker，新代码请直接使用新路径。"""

import sys
from importlib import import_module

if __name__ == "__main__":
    import asyncio

    asyncio.run(import_module("backend.infrastructure.jobs.worker").main())
else:
    sys.modules[__name__] = import_module("backend.infrastructure.jobs.worker")
