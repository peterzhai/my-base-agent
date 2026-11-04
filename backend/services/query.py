"""旧查询能力兼容入口；不再保留第二份实现。"""

from backend.capabilities.data_query.compiler import compile_query as compile_query
from backend.capabilities.data_query.executor import execute_readonly as execute_readonly
from backend.capabilities.data_query.service import query_data as query_data
