# 策略与守卫模块

## 职责

声明身份和授权策略接口，并统一预算、取消与实时权限检查。

## 依赖与公开边界

通过回调取得外部状态；不依赖 ORM 或 HTTPException。

## 阅读顺序与使用说明

contracts.py:Principal/ExecutionPolicy；guard.py:ExecutionGuard。ExecutionPolicy 仍是预留授权端口。

## 文件清单

- `__init__.py`
- `contracts.py`
- `guard.py`

## 学习要点

通过公开协议或明确入口组合能力，避免跨层访问内部存储。阅读函数注释中的权限、异常、事务和恢复约束；新增实现必须保持这些契约。目录的存在不代表该能力具备自主决策循环。
