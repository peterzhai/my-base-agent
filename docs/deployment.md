# Windows Server 内网部署

## 准备

在 Hyper-V 中建立 Linux 虚拟机，给应用分配 4 核 8GB；Windows 宿主资源另行预留。本文按 x86_64 Linux 部署，磁盘容量按原始资料、数据库向量、索引世代与备份预留。安装 Docker Engine 与 Compose 插件。现有 MySQL 在内网独立地址提供服务，不需要再创建 MySQL 容器。

DBA 审阅 `deploy/mysql-bootstrap.sql`，替换账号密码和来源地址限制后执行。平台库使用 utf8mb4；迁移账号需要在该平台库执行 DDL 和创建 FULLTEXT 索引，不能给它业务库写权限。业务查询账号只授予已审查表/视图的 SELECT。

## 联网构建、离线搬运

在与目标架构一致的联网 Linux 构建机执行：

```bash
bash scripts/build-offline.sh /path/to/offline-bundle
```

Python 依赖版本与哈希来自 deploy/requirements.lock；Node 依赖来自 package-lock.json。镜像含运行依赖，工厂内网启动时无需访问软件仓库。ARM 开发机应在 x86_64 构建机执行打包，避免装入错误架构镜像。

离线复制 bundle 到 Linux 虚拟机：

```bash
docker load -i images.tar
cp .env.example .env
mkdir -p data
sudo chown 10001:10001 data
```

编辑 `.env`：填写现有 MySQL 连接串，设置独立 JWT_SECRET、SERVICE_KEY、ADMIN_PASSWORD 和 Fernet ENCRYPTION_KEY，配置宿主允许的 origin。示例占位符必须替换；密码中的特殊字符需要 URL 编码。DATA_DIR 固定为 /app/data，恢复时保持相同容器路径。

可使用镜像生成 Fernet 密钥：

```bash
docker run --rm factory-agent-api:0.1.0 python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

初始化并启动：

```bash
docker compose run --rm --no-deps api alembic upgrade head
docker compose run --rm --no-deps api python -m backend.bootstrap
docker compose up -d --no-build
docker compose ps
```

访问 `http://虚拟机地址:8080`，用 ADMIN_PASSWORD 登录。内网 HTTPS 应由已有网关或反向代理提供；正确转发 API 路由并关闭 SSE 缓冲。生产部署不启动示例宿主、不导入 demo 数据。

## 接入真实服务

1. 配置 default 模型为 openai-compatible，填写 `/v1` 服务根地址、聊天与向量模型 ID 及密钥，运行“测试接口”。生产引导保留标注为模拟的占位模型，必须完成此步骤才做真实效果验收。
2. 配置用户、角色、部门和宿主身份映射。
3. 配置知识库权限，上传资料并检查后台任务。
4. 配置独立只读数据源，以及允许的业务主题、部门字段和口径。
5. 将组件 tgz 交给宿主工程，完成后端身份交换并验证账号切换。

## 运行与容量

API 使用一个 worker，后台导入一个进程，模型调用最多同时 4 个；每次 Agent 运行默认 90 秒。Compose 的 API、worker、web 内存限额分别为 1800MB、2600MB、128MB，其余留给系统、缓存及文件处理。独立 MySQL 和模型服务另计资源。

管理后台可看任务、审计及评测；管理员令牌访问 `/api/v1/metrics` 获取模型耗时与 token 统计。HTTP 日志包含 trace ID、路径、状态和耗时，不记录凭据和原始 SQL。生产不能开启 LangSmith 外部 tracing。

50,000 文本块和 5–10 并发是容量验收基线，不代表未经目标机器测试即可保证的 SLA。向量维度、原文长度、模型服务吞吐和业务数据库索引都影响资源消耗。先运行 scripts/benchmark.py 的本地合成检索测试，再在目标环境执行 HTTP 压测，并验证后台导入同时运行时的内存及超时。

## 备份恢复

备份主数据时先停止写入：`docker compose stop api worker`。在能访问 MySQL、具有 MySQL 8 mysqldump/mysql 客户端、Python 项目依赖和 `.env` 的维护环境运行：

```bash
python -m scripts.backup backup /secure-backups/platform.tar.gz
python -m scripts.backup restore /secure-backups/platform.tar.gz --confirm-restore
```

备份应包含平台数据库和 data 原始文件；索引是派生缓存，恢复后在后台重建。脚本不备份 `.env`，必须另行安全保存原加密密钥；丢失密钥会导致数据源和模型凭据无法解密。备份文件本身含业务内容，需要按工厂备份权限存放。

恢复到已创建的平台库，保持原 DATA_DIR 和密钥；运行迁移检查后启动 API/worker，重建索引并抽查文档引用、部门权限及查询结果。备份恢复演练必须使用独立测试平台库，不能在正在使用的业务库上操作。
