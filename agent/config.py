from functools import lru_cache
from typing import Optional
from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """
    生产级全局配置规范：
    1. 强类型断言
    2. 密钥类型脱敏 (SecretStr)
    3. 环境变量自动解析与校验
    """
    # 必填项：如果 .env 没配或环境变量为空，启动阶段直接抛出 ValidationError 熔断
    api_key: SecretStr = Field(..., alias="API_KEY", description="大模型平台调用凭证")
    
    # 带默认值与 URL 校验的字段
    api_url: HttpUrl = Field(
        default="https://api.deepseek.com", 
        alias="API_URL", 
        description="大模型网关 Base URL"
    )
    model_name: str = Field(
        default="deepseek-chat", 
        alias="MODEL_NAME"
    )
    
    # 强转为整数，并限制取值边界
    max_turns: int = Field(
        default=5, 
        ge=1, 
        le=20, 
        alias="MAX_TURNS", 
        description="Agent 最大反思决策轮次"
    )
    is_debug: bool = Field(
        default=False, 
        alias="DEBUG"
    )

    # 读取 .env 文件规则
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",          # 忽略环境变量里多余的杂项
        case_sensitive=False     # 大小写不敏感（API_KEY 和 api_key 都能认）
    )


# 单例模式注入配置（避免每次 import 重复解析 IO）
@lru_cache()
def get_settings() -> AppSettings:
    return AppSettings()


# 实例化配置
settings = get_settings()

# 使用安全提取的明文凭证初始化 Client
from openai import OpenAI

client = OpenAI(
    api_key=settings.api_key.get_secret_value(),  # 只有在真正发起物理网络请求时才解密
    base_url=str(settings.api_url)
)