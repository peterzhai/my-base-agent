"""受控查询语言与业务主题，所有标识符必须通过白名单校验。"""

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def identifier(value: str) -> str:
    """仅接受普通标识符语法；这不代替字段白名单，两层限制共同阻止标识符注入。"""
    if not IDENT.fullmatch(value):
        raise ValueError("非法数据库标识符")
    return value


class Filter(BaseModel):
    """查询语言中的单个谓词，只允许枚举运算符与绑定值。"""

    field: str
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"]
    value: str | int | float | list[str | int | float]


class QueryPlan(BaseModel):
    """模型输出的闭合查询计划；没有原始 SQL 或任意表达式入口。"""

    dimensions: list[str] = Field(default_factory=list, max_length=10)
    metrics: list[str] = Field(default_factory=list, max_length=10)
    filters: list[Filter] = Field(default_factory=list, max_length=20)
    order_by: list[dict[str, str]] = Field(default_factory=list, max_length=5)
    limit: int = Field(default=100, ge=1, le=200)
    clarification: str = ""


class Join(BaseModel):
    """管理员预先审核的表关联，只允许指定别名和等值字段关联。"""

    table: str
    alias: str
    left: str
    right: str
    kind: Literal["inner", "left"] = "inner"


class Metric(BaseModel):
    """受控聚合指标；聚合函数来自枚举，字段来自白名单。"""

    field: str
    aggregate: Literal["sum", "avg", "min", "max", "count"]
    label: str = ""


class TopicConfig(BaseModel):
    """业务主题配置，定义查询范围和统计口径；保存前验证引用一致性。"""

    enabled: bool = False
    roles: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    datasource_id: str
    table: str
    alias: str = "t"
    fields: dict[str, str]
    dimensions: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, Metric] = Field(default_factory=dict)
    joins: list[Join] = Field(default_factory=list, max_length=5)
    department_field: str
    time_field: str | None = None
    description: str = ""

    @model_validator(mode="after")
    def validate_identifiers(self):
        """验证主题表别名、字段、关联、指标与部门字段的一致性，拒绝无法安全编译的配置。"""
        identifier(self.table)
        aliases = {identifier(self.alias)}
        for join in self.joins:
            identifier(join.table)
            alias = identifier(join.alias)
            if alias in aliases:
                raise ValueError("关联别名重复")
            aliases.add(alias)
        for key, column in self.fields.items():
            identifier(key)
            parts = column.split(".")
            if len(parts) != 2 or parts[0] not in aliases:
                raise ValueError("字段必须是已配置表别名.字段名")
            identifier(parts[1])
        if self.department_field not in self.fields:
            raise ValueError("必须配置有效的部门权限字段")
        if self.time_field and self.time_field not in self.fields:
            raise ValueError("时间字段未配置")
        for join in self.joins:
            if join.left not in self.fields or join.right not in self.fields:
                raise ValueError("关联只能引用允许的字段")
        for key in self.dimensions:
            if key not in self.fields:
                raise ValueError("维度字段未配置")
        for key, metric in self.metrics.items():
            identifier(key)
            if metric.field not in self.fields or key in self.fields:
                raise ValueError("指标字段未配置或指标名与字段名冲突")
        return self
