"""确定性查询编译器：标识符取自主题白名单，值使用绑定参数。"""

from backend.bootstrap.settings import settings
from backend.capabilities.data_query.schemas import QueryPlan, TopicConfig


def compile_query(topic: TopicConfig, plan: QueryPlan, department: str) -> tuple[str, dict]:
    """Compile a closed query language. No SQL fragments or identifiers come from model output."""
    if not department:
        raise PermissionError("未配置部门，禁止业务查询")
    fields = {key: ".".join(f"`{part}`" for part in value.split(".")) for key, value in topic.fields.items()}
    select_parts, group = [], []
    for name in plan.dimensions:
        if name not in topic.dimensions:
            raise ValueError("查询维度不在白名单内")
        select_parts.append(f"{fields[name]} AS `{name}`")
        group.append(fields[name])
    for name in plan.metrics:
        if name not in topic.metrics:
            raise ValueError("查询指标不在白名单内")
        metric = topic.metrics[name]
        select_parts.append(f"{metric.aggregate.upper()}({fields[metric.field]}) AS `{name}`")
    if not select_parts:
        raise ValueError("请指定查询字段或指标")
    sql = f"SELECT /*+ MAX_EXECUTION_TIME({settings().query_timeout_seconds * 1000}) */ "
    sql += ", ".join(select_parts) + f" FROM `{topic.table}` AS `{topic.alias}`"
    for join in topic.joins:
        sql += f" {join.kind.upper()} JOIN `{join.table}` AS `{join.alias}` ON {fields[join.left]} = {fields[join.right]}"
    predicates = [f"{fields[topic.department_field]} = :_department"]
    params: dict = {"_department": department}
    ops = {"eq": "=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    for i, item in enumerate(plan.filters):
        if item.field not in fields:
            raise ValueError("筛选字段不在白名单内")
        name = f"p{i}"
        if item.op == "in":
            if not isinstance(item.value, list) or not 1 <= len(item.value) <= 100:
                raise ValueError("IN 筛选需要 1–100 个值")
            names = [f"{name}_{j}" for j in range(len(item.value))]
            params.update(zip(names, item.value))
            predicates.append(f"{fields[item.field]} IN ({', '.join(':' + n for n in names)})")
        else:
            if isinstance(item.value, list):
                raise ValueError("此筛选不接受列表")
            if item.op == "contains":
                params[name] = (
                    "%" + str(item.value).replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
                )
                predicates.append(f"{fields[item.field]} LIKE :{name} ESCAPE '!'")
            else:
                params[name] = item.value
                predicates.append(f"{fields[item.field]} {ops[item.op]} :{name}")
    sql += " WHERE " + " AND ".join(predicates)
    if group:
        sql += " GROUP BY " + ", ".join(group)
    output_names = set(plan.dimensions + plan.metrics)
    orders = []
    for order in plan.order_by:
        if order.get("field") not in output_names or order.get("direction", "asc").lower() not in (
            "asc",
            "desc",
        ):
            raise ValueError("非法排序")
        orders.append(f"`{order['field']}` {order.get('direction', 'asc').upper()}")
    if orders:
        sql += " ORDER BY " + ", ".join(orders)
    params["_limit"] = min(plan.limit, settings().max_query_rows) + 1
    return sql + " LIMIT :_limit", params
