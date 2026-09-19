from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "电商运营助手"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "127.0.0.1"
    app_port: int = 8011
    app_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    database_host: str = "127.0.0.1"
    database_port: int = 3306
    database_name: str = "ecommerce_ops"
    database_user: str = "ecommerce_dev"
    database_password: SecretStr = Field(default=SecretStr(""))
    database_echo: bool = False

    jwt_secret: SecretStr = Field(
        default=SecretStr("development-only-change-me-development-only-change-me")
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 120

    llm_model: str = "mock"
    llm_structured_model: str = "qwen-plus"
    llm_base_url: str = ""
    llm_api_key: SecretStr = Field(default=SecretStr(""))
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 2
    llm_requests_per_minute: int = 30
    llm_max_input_chars: int = 30000
    llm_max_output_tokens: int = 4096

    storage_backend: str = "local"
    storage_local_path: Path = PROJECT_ROOT / "storage"
    storage_download_timeout_seconds: int = 30
    storage_max_redirects: int = 3
    storage_max_image_bytes: int = 20_000_000
    storage_max_video_bytes: int = 100_000_000
    generation_provider: str = "dashscope"
    image_model: str = "qwen-image-3.0"
    image_size: str = "1024x1024"
    video_model: str = "wan2.6-t2v"
    video_size: str = "1280*720"
    video_duration_seconds: int = 5

    job_max_attempts: int = 3
    job_timeout_seconds: int = 900
    job_poll_interval_seconds: int = 3
    job_lock_timeout_seconds: int = 120
    job_worker_concurrency: int = 2

    competitor_parse_allowed_domains: str = (
        "taobao.com,tmall.com,jd.com,pinduoduo.com,douyin.com,"
        "kuaishou.com,xiaohongshu.com,weixin.qq.com"
    )
    competitor_parse_timeout_seconds: int = 10
    competitor_parse_max_bytes: int = 2_000_000
    competitor_parse_max_redirects: int = 3

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.app_cors_origins.split(",") if origin.strip()]

    @property
    def competitor_allowed_domains(self) -> list[str]:
        return [
            domain.strip().lower().lstrip(".")
            for domain in self.competitor_parse_allowed_domains.split(",")
            if domain.strip()
        ]

    def validate_runtime(self) -> None:
        errors: list[str] = []
        if not self.database_name or not self.database_user:
            errors.append("数据库名称和用户名不能为空。")
        if not self.database_password.get_secret_value():
            errors.append("DATABASE_PASSWORD 未配置。")
        if len(self.jwt_secret.get_secret_value()) < 32:
            errors.append("JWT_SECRET 至少需要 32 个字符。")
        if self.generation_provider == "dashscope" and not self.llm_api_key.get_secret_value():
            errors.append("使用 DashScope 时必须配置 LLM_API_KEY。")
        if self.generation_provider not in {"mock", "dashscope"}:
            errors.append("GENERATION_PROVIDER 仅支持 mock 或 dashscope。")
        if self.storage_backend != "local":
            errors.append("当前 STORAGE_BACKEND 仅支持 local。")
        if self.app_env == "production" and self.app_debug:
            errors.append("生产环境必须关闭 APP_DEBUG。")
        if errors:
            raise RuntimeError("运行配置无效：" + "；".join(errors))


@lru_cache
def get_settings() -> Settings:
    return Settings()
