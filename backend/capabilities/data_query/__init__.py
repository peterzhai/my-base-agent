"""受控查询公开 API；不公开原始数据库连接或绕过授权的 HTTP 接口。"""

from backend.capabilities.data_query.compiler import compile_query as compile_query
from backend.capabilities.data_query.executor import execute_readonly as execute_readonly
from backend.capabilities.data_query.service import query_data as query_data
