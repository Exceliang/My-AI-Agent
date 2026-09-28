from functools import lru_cache
from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    api_key: SecretStr = Field(..., alias="API_KEY")
    api_url: HttpUrl = Field(default="https://api.siliconflow.cn/v1", alias="API_URL")
    model_name: str = Field(default="deepseek-ai/DeepSeek-V4-Flash", alias="MODEL_NAME")
    max_turns: int = Field(default=5, ge=1, le=20, alias="MAX_TURNS")
    is_debug: bool = Field(default=False, alias="DEBUG")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )


@lru_cache()
def get_settings() -> AppSettings:
    """按需延迟加载配置单例"""
    return AppSettings()