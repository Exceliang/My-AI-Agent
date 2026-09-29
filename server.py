import json
import traceback
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.engine import AgentEngine
from config import get_settings

app = FastAPI(
    title="Semiconductor Quant Analysis Agent API",
    description="工业级半导体 Text-to-SQL 量化分析智能体 Web 服务",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = AgentEngine()


class AnalysisRequest(BaseModel):
    query: str = Field(..., description="投研自然语言指令")


class AnalysisResponse(BaseModel):
    query: str
    report: str


@app.get("/health")
def health_check():
    return {"status": "healthy", "model": get_settings().model_name}


@app.post("/api/v1/analyze", response_model=AnalysisResponse)
async def analyze_sync(payload: AnalysisRequest):
    try:
        report = engine.run(payload.query)
        return AnalysisResponse(query=payload.query, report=report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/analyze/stream")
async def analyze_stream(payload: AnalysisRequest):
    """
    FastAPI 原生 SSE 流式端点
    使用标准 text/event-stream 协议，加装全局异常捕获，绝不中途断连
    """
    async def sse_event_generator():
        try:
            async for item in engine.run_stream(payload.query):
                event_name = item["event"]
                data_str = json.dumps(item["data"], ensure_ascii=False)
                # 遵循标准 SSE 报文规范: event: <type>\ndata: <json>\n\n
                yield f"event: {event_name}\ndata: {data_str}\n\n"
        except Exception as e:
            # 打印到控制台，方便服务端调试
            print("\n[服务端异常捕获]:")
            traceback.print_exc()
            
            # 优雅推给客户端，避免 HTTP Chunked 连接粗暴中断
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