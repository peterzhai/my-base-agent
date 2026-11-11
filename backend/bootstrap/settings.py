"""环境配置边界：开发允许 SQLite，生产必须显式提供 MySQL、密钥与宿主来源。配置在启动时校验，避免运行中才发现危险默认值。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """环境配置值对象：负责默认值、类型和生产约束，不提供业务操作。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite:///./data/platform.db"
    data_dir: Path = Path("data")
    jwt_secret: str = "development-only-change-this-secret-at-least-32"
    encryption_key: str = ""  # Fernet key; required in production
    service_key: str = "development-service-key"
    admin_password: str = "111111"
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    token_minutes: int = 15
    max_upload_mb: int = 20
    max_chunks: int = 50000
    model_concurrency: int = 4
    query_timeout_seconds: int = 10
    max_query_rows: int = 200

    def validate_production(self):
        """拒绝占位密钥、开发凭据、不合规数据库和通配来源，提前暴露部署配置问题。"""
        if self.environment == "production":
            from cryptography.fernet import Fernet

            values = [self.jwt_secret, self.service_key, self.admin_password, self.encryption_key]
            if any("REPLACE" in value or "development" in value.lower() for value in values):
                raise ValueError("生产配置中的默认值与占位符必须替换")
            try:
                Fernet(self.encryption_key)
            except (ValueError, TypeError):
                raise ValueError("ENCRYPTION_KEY 必须是有效 Fernet 密钥") from None
            if not self.database_url.startswith("mysql+pymysql://"):
                raise ValueError("生产环境必须使用 MySQL")
            if "development" in self.jwt_secret or len(self.jwt_secret) < 32:
                raise ValueError("必须配置 JWT_SECRET")
            if not self.encryption_key or "development" in self.service_key or len(self.service_key) < 24:
                raise ValueError("必须配置 ENCRYPTION_KEY 和 SERVICE_KEY")
            if len(self.admin_password) < 16 or "development" in self.admin_password:
                raise ValueError("必须配置 ADMIN_PASSWORD")
            if "*" in self.allowed_origins.split(","):
                raise ValueError("生产环境必须明确配置允许的宿主 origin")


@lru_cache
def settings() -> Settings:
    """缓存经校验的进程配置并创建数据目录，减少每次请求重复读取环境。"""
    value = Settings()
    value.validate_production()
    value.data_dir.mkdir(parents=True, exist_ok=True)
    return value
