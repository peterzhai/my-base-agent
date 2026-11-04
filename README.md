# 工厂 Agent 基础底座

可复用的 Python Agent 核心、LangGraph 编排、MySQL 8.0.31 平台存储与 FAISS RAG，附 React + Ant Design 管理后台和独立聊天组件。

首期支持带引用的系统知识问答、按部门隔离的受控业务查询，以及两者的串行/并行混合问答。默认模拟模型仅用于本地演示，回答有明确标记；真实模型通过内网 OpenAI-compatible 接口配置。

## 架构与交接

**当前目录入口：[模块化目录与交付导航](docs/module-map.md)**。各模块目录均有 README，明确职责、公开入口、依赖方向和实现边界。

当前重构结构与学习入口：[面向对象设计与源码学习指南](docs/design-principles.md)。涵盖七项原则、实际采用的设计模式、目录映射与阅读顺序。

先阅读 [项目交付说明书](docs/delivery-guide.md)，其中区分实际目录、当前执行链路、完整 Agent 参考架构与尚未实现的模块。当前版本是受控问答工作流与基础能力原型，不具备完整的通用自主 Agent 闭环。

## 本地启动

需要 Python 3.12、uv、Node.js 22。默认使用 SQLite 开发适配器，不需要先配置工厂数据库。

```bash
uv sync --extra dev --python 3.12
cp .env.example .env
uv run alembic upgrade head
uv run python -m backend.bootstrap --demo --drain-jobs
npm ci
```

分别在终端启动：

```bash
uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000
uv run python -m backend.infrastructure.jobs.worker
uv run uvicorn examples.host_server:app --host 127.0.0.1 --port 8001
npm run dev
```

- 管理后台：<http://127.0.0.1:5173>，开发管理员密码 `development-admin-password`。
- 组件接入示例：<http://127.0.0.1:5173/demo>，可切换一、二车间员工验证隔离。
- API 文档：<http://127.0.0.1:8000/docs>。
- 示例提问：`MES 如何报工？`、`今天产量是多少？`、`各物料库存是多少？`。
- 一车间演示产量为 200，二车间为 999；两者不会跨部门返回。

## 验证与构建

```bash
uv run pytest -q
uv run ruff check backend examples migrations scripts tests
npm run typecheck
npm run build
npm run test:e2e
uv run python -m scripts.benchmark --chunks 50000 --concurrency 10
```

浏览器测试默认使用本机 Chrome；可用 PLAYWRIGHT_CHROMIUM_EXECUTABLE 指定可执行文件，或先安装 Playwright Chromium。测试自动启动隔离的 API 和示例宿主，使用临时数据目录，不访问真实业务库。

仓库目录：`backend/agent` 通用内核、`backend/capabilities` 知识与查询能力、`backend/infrastructure` 技术适配、`backend/applications` 工厂应用、`packages/chat` 聊天组件、`web` 管理后台、`migrations` 平台迁移、`deploy` 离线部署配置、`tests` 回归测试。

## 生产接入

生产必须配置 MySQL、密钥和独立管理员密码；不会自动加载演示业务数据。执行迁移和 bootstrap 后，在后台配置真实模型、数据源、业务主题、授权与宿主映射。

详见 [架构与权限](docs/architecture.md)、[React 集成](docs/integration.md)、[Windows Server 离线部署](docs/deployment.md)。实现边界与实际验证结果见 [验收记录](docs/validation.md)。
