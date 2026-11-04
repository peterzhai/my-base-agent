#!/usr/bin/env bash
# 失败即停止：避免把构建失败的镜像误标为已完成交付。
set -euo pipefail
cd "$(dirname "$0")/.."
out="${1:-offline-bundle}"
mkdir -p "$out"
# Build without requiring a production .env on the build machine.
target_platform="${TARGET_PLATFORM:-linux/amd64}"
docker build --platform "$target_platform" -f deploy/Dockerfile.api -t factory-agent-api:0.1.0 .
docker build --platform "$target_platform" -f deploy/Dockerfile.web -t factory-agent-web:0.1.0 .
# 镜像包含运行依赖；内网只需 load，不应再次访问软件仓库。
docker save factory-agent-api:0.1.0 factory-agent-web:0.1.0 -o "$out/images.tar"
cp compose.yaml "$out/compose.yaml"
cp deploy/production.env.example "$out/.env.example"
cp deploy/mysql-bootstrap.sql "$out/mysql-bootstrap.sql"
cp -R docs "$out/docs"
mkdir -p "$out/components"
cp artifacts/factory-agent-chat-0.1.0.tgz "$out/components/"
# 流式计算校验值，避免一次把数百 MB 镜像加载到内存。
python3 - "$out" <<'PY'
import hashlib
import pathlib
import sys
root = pathlib.Path(sys.argv[1])
lines = []
for path in sorted(root.rglob('*')):
    if path.is_file() and path.name != 'SHA256SUMS':
        digest = hashlib.sha256()
        with path.open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(block)
        lines.append(f'{digest.hexdigest()}  {path.relative_to(root).as_posix()}')
(root / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
PY
printf '%s\n' 'Offline bundle ready. See docs/deployment.md.'
