from functools import lru_cache
from openai import OpenAI, AsyncOpenAI
from config import get_settings


@lru_cache()
def get_llm_client() -> OpenAI:
    """
    同步客户端单例工厂：
    只有在代码真正调用 get_llm_client() 时才物理创建连接，
    避免 import 时产生任何副作用。
    """
    settings = get_settings()
    # 修正 HttpUrl 转换字符串后可能带有的末尾斜杠
    base_url = str(settings.api_url).rstrip("/")
    
    return OpenAI(
        api_key=settings.api_key.get_secret_value(),
        base_url=base_url
    )


@lru_cache()
def get_async_llm_client() -> AsyncOpenAI:
    """
    异步客户端单例工厂：专为 FastAPI / SSE 实时流式并发设计
    """
    settings = get_settings()
    base_url = str(settings.api_url).rstrip("/")
    
    return AsyncOpenAI(
        api_key=settings.api_key.get_secret_value(),
        base_url=base_url
    )