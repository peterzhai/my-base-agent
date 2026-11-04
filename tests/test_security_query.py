"""回归测试：使用隔离数据验证行为契约；重点覆盖权限、失败和恢复路径，不能连接工厂业务库。"""

import pytest

from backend.infra.db import Session
from backend.infra.models import Record
from backend.infra.security import allowed, decrypt, principal_for_user
from backend.services.query import compile_query, execute_readonly
from backend.services.schemas import QueryPlan, TopicConfig


def config():
    """config 是本模块的辅助步骤；其调用位置与事务/异常边界由上层流程控制。"""
    with Session() as db:
        return TopicConfig.model_validate(db.get(Record, ("topics", "production")).config)


def test_department_is_forced_even_on_admin():
    """验证 department is forced even on admin 的行为契约；断言失败表示该路径的约束被破坏。"""
    topic = config()
    plan = QueryPlan(metrics=["total_produced"])
    sql, params = compile_query(topic, plan, "workshop-a")
    with Session() as db:
        url = decrypt(db.get(Record, ("datasources", "demo")).config["url_encrypted"])
    assert execute_readonly(url, sql, params) == [{"total_produced": 200}]
    _, params = compile_query(topic, plan, "workshop-b")
    assert execute_readonly(url, sql, params) == [{"total_produced": 999}]


def test_sql_injection_stays_in_bound_parameter():
    """验证 sql injection stays in bound parameter 的行为契约；断言失败表示该路径的约束被破坏。"""
    topic = config()
    plan = QueryPlan(
        metrics=["total_produced"], filters=[{"field": "workshop", "op": "eq", "value": "x' OR 1=1 --"}]
    )
    sql, params = compile_query(topic, plan, "workshop-a")
    assert "OR 1=1" not in sql
    assert params["p0"] == "x' OR 1=1 --"
    assert params["_department"] == "workshop-a"


@pytest.mark.parametrize(
    "plan",
    [
        {"dimensions": ["password"]},
        {"metrics": ["sum(produced)"]},
        {"dimensions": ["workshop; DROP TABLE x"]},
        {"metrics": ["total_produced"], "filters": [{"field": "unknown", "op": "eq", "value": 1}]},
        {
            "metrics": ["total_produced"],
            "order_by": [{"field": "total_produced", "direction": "desc;delete"}],
        },
    ],
)
def test_disallowed_model_fields_are_rejected(plan):
    """验证 disallowed model fields are rejected 的行为契约；断言失败表示该路径的约束被破坏。

    plan：经过校验的结构化查询计划"""
    with pytest.raises(ValueError):
        compile_query(config(), QueryPlan.model_validate(plan), "workshop-a")


def test_topic_cannot_enable_without_department_mapping():
    """验证 topic cannot enable without department mapping 的行为契约；断言失败表示该路径的约束被破坏。"""
    payload = config().model_dump()
    payload["department_field"] = "unconfigured"
    with pytest.raises(ValueError):
        TopicConfig.model_validate(payload)


def test_only_registered_table_identifiers():
    """验证 only registered table identifiers 的行为契约；断言失败表示该路径的约束被破坏。"""
    payload = config().model_dump()
    payload["table"] = "orders; DROP TABLE users"
    with pytest.raises(ValueError):
        TopicConfig.model_validate(payload)


def test_acl_is_deny_by_default_and_intersects_roles_departments():
    """验证 acl is deny by default and intersects roles departments 的行为契约；断言失败表示该路径的约束被破坏。"""
    user = principal_for_user("demo-a")
    assert not allowed(user, {})
    assert not allowed(user, {"roles": ["employee"], "departments": ["workshop-b"]})
    assert allowed(user, {"roles": ["employee"], "departments": ["workshop-a"]})


def test_preconfigured_join_and_grouping():
    """验证 preconfigured join and grouping 的行为契约；断言失败表示该路径的约束被破坏。"""
    topic = config().model_dump()
    topic["joins"] = [
        {
            "table": "workshops",
            "alias": "w",
            "left": "department",
            "right": "workshop_department",
            "kind": "left",
        }
    ]
    topic["fields"]["workshop_department"] = "w.department"
    sql, _ = compile_query(
        TopicConfig.model_validate(topic),
        QueryPlan(dimensions=["workshop"], metrics=["total_produced"]),
        "workshop-a",
    )
    assert "LEFT JOIN `workshops`" in sql
    assert "GROUP BY `t`.`workshop`" in sql
