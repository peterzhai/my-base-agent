"""Run on a maintenance host with MySQL 8 client tools and the platform .env.

Stop API/worker first; credentials are passed in child-process env, never CLI args.
"""

import argparse
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path

from sqlalchemy.engine import make_url

from backend.config import settings


def mysql_command(program):
    """从配置构造 MySQL 客户端参数，密码仅置于子进程环境，不拼入命令字符串。"""
    url = make_url(settings().database_url)
    if not url.drivername.startswith("mysql"):
        raise ValueError("此脚本只备份 MySQL；开发 SQLite 可停机复制 data 目录")
    args = [
        program,
        "--host",
        url.host or "localhost",
        "--port",
        str(url.port or 3306),
        "--user",
        url.username or "",
        "--default-character-set=utf8mb4",
    ]
    return args, {**os.environ, "MYSQL_PWD": url.password or ""}, url.database


def backup(destination):
    """在维护窗口导出平台库并打包原始资料；索引可重建，环境密钥须另外安全保存。"""
    with tempfile.TemporaryDirectory() as folder:
        sql = Path(folder) / "platform.sql"
        args, env, database = mysql_command("mysqldump")
        with sql.open("wb") as output:
            subprocess.run(
                args + ["--single-transaction", "--no-tablespaces", "--set-gtid-purged=OFF", database],
                env=env,
                stdout=output,
                check=True,
            )
        with tarfile.open(destination, "w:gz") as archive:
            archive.add(sql, arcname="platform.sql")
            archive.add(
                settings().data_dir,
                arcname="data",
                filter=lambda item: None if "/indexes/" in item.name else item,
            )
    print("备份完成；请单独安全保存 .env 与加密密钥。")


def restore(source, confirmed):
    """要求显式确认后导入平台库并恢复原始资料；应在停机和正确目标库下执行。"""
    if not confirmed:
        raise ValueError("恢复会覆盖平台数据，请停机并传入 --confirm-restore")
    with tempfile.TemporaryDirectory() as folder:
        with tarfile.open(source, "r:gz") as archive:
            archive.extractall(folder, filter="data")
        args, env, database = mysql_command("mysql")
        with (Path(folder) / "platform.sql").open("rb") as sql:
            subprocess.run(args + [database], env=env, stdin=sql, check=True)
        import shutil

        shutil.copytree(Path(folder) / "data", settings().data_dir, dirs_exist_ok=True)
    print("恢复完成；启动后在管理后台重建索引。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["backup", "restore"])
    parser.add_argument("path")
    parser.add_argument("--confirm-restore", action="store_true")
    args = parser.parse_args()
    backup(args.path) if args.action == "backup" else restore(args.path, args.confirm_restore)
