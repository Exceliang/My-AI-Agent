import asyncio
import json
import traceback
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import get_settings
from core.engine import AgentEngine

app = FastAPI(
    title="Investment Analysis Agent",
    description="投资分析智能体",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 1. 依赖注入：确保每个请求拥有独立的 Engine 实例，消除并发会话与状态污染
def get_engine() -> AgentEngine:
    return AgentEngine()


class AnalysisRequest(BaseModel):
    query: str = Field(..., description="投研自然语言指令")


class AnalysisResponse(BaseModel):
    query: str
    report: str


@app.get("/health")
def health_check():
    return {"status": "healthy", "model": get_settings().model_name}


@app.post("/api/v1/analyze", response_model=AnalysisResponse)
async def analyze_sync(
    payload: AnalysisRequest,
    engine: AgentEngine = Depends(get_engine)
):
    """
    同步分析接口：
    使用 asyncio.to_thread 将阻塞式的 ReAct 循环丢入线程池，绝不锁死主事件循环
    """
    try:
        report = await asyncio.to_thread(engine.run, payload.query)
        return AnalysisResponse(query=payload.query, report=report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/analyze/stream")
async def analyze_stream(
    payload: AnalysisRequest,
    request: Request,
    engine: AgentEngine = Depends(get_engine)
):
    """
    FastAPI 原生 SSE 流式端点：
    挂载客户端断开感知（is_disconnected），支持异常边界兜底与代理直通
    """
    async def sse_event_generator() -> AsyncGenerator[str, None]:
        try:
            async for item in engine.run_stream(payload.query):
                # 核心改进：主动监听客户端连接状态，网页关闭或取消时立即掐断后台 Token 消耗
                if await request.is_disconnected():
                    print(f"\n[SSE 警告]: 客户端已主动断开，终止后序推理: {payload.query[:20]}...")
                    break

                event_name = item.get("event", "message")
                data_str = json.dumps(item.get("data", {}), ensure_ascii=False)
                
                # 遵循标准 SSE 报文规范
                yield f"event: {event_name}\ndata: {data_str}\n\n"

        except Exception as e:
            print("\n[服务端异常捕获]:")
            traceback.print_exc()

            err_payload = json.dumps({
                "message": f"服务端推理中途异常: {str(e)}",
                "type": type(e).__name__
            }, ensure_ascii=False)
            
            yield f"event: error\ndata: {err_payload}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': 'failed'})}\n\n"

    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)