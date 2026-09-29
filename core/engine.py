import json
import asyncio
from typing import AsyncGenerator, Dict, Any, List
from core.client import get_llm_client, get_async_llm_client
from config import get_settings
from tools.registry import TOOL_MAP, TOOLS_SCHEMA


class AgentEngine:
    def __init__(self, max_turns: int | None = None):
        self.settings = get_settings()
        self.client = get_llm_client()
        self.async_client = get_async_llm_client()
        self.max_turns = max_turns or 10

    def _get_system_prompt(self) -> str:
        return (
            "你是一个资深量化投资与财务分析专家，物理底座为 DuckDB 分析数据库。\n"
            "工作准则:\n"
            "1. 物理表名唯一确定为 `market`，全表均为产业链标的。\n"
            "2. 查询前必须调 get_db_schema 确认物理字段与公式，严禁臆造不存在的预计算列。\n"
            "3. 真实自由现金流(FCF)、ROIC、负债率等指标需在 SQL 中推导，除法必须用 NULLIF(col, 0) 保护。\n"
            "4. 收到 SQL 报错时自行分析并自愈重写。\n"
            "5. 获取数据后输出结构化 Markdown 研报。"
        )

    # ==================== 1. CLI 同步运行入口 ====================
    def run(self, query: str) -> str:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": query}
        ]

        for step in range(1, self.max_turns + 1):
            response = self.client.chat.completions.create(
                model=self.settings.model_name,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.1
            )
            msg = response.choices[0].message
            messages.append(msg)

            if not msg.tool_calls:
                return msg.content

            for tool_call in msg.tool_calls:
                func_name = tool_call.function.name
                args_str = tool_call.function.arguments
                call_id = tool_call.id

                try:
                    args_dict = json.loads(args_str)
                    target_func = TOOL_MAP.get(func_name)
                    if not target_func:
                        raise NotImplementedError(f"未注册工具: {func_name}")
                    tool_output = target_func(**args_dict)
                except Exception as err:
                    tool_output = json.dumps({"error": f"系统调度异常: {str(err)}"}, ensure_ascii=False)

                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": tool_output
                })

        return "【系统熔断】超过最大 ReAct 决策轮次，执行已强制中止。"

    # ==================== 2. FastAPI SSE 异步流式生成器 ====================
    async def run_stream(self, query: str) -> AsyncGenerator[Dict[str, Any], None]:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": query}
        ]

        for turn in range(1, self.max_turns + 1):
            # 推送思考进度
            yield {
                "event": "thought",
                "data": {"turn": turn, "message": f"正在进行第 {turn}/{self.max_turns} 轮分析决策..."}
            }

            # 异步调用大模型
            response = await self.async_client.chat.completions.create(
                model=self.settings.model_name,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.1
            )
            msg = response.choices[0].message
            messages.append(msg)

            # 模型决策结束，直接推送最终投研研报
            if not msg.tool_calls:
                yield {
                    "event": "report",
                    "data": {"content": msg.content}
                }
                yield {"event": "done", "data": {"status": "success"}}
                return

            # 分发并异步执行工具调用
            for tool_call in msg.tool_calls:
                func_name = tool_call.function.name
                raw_args = tool_call.function.arguments
                call_id = tool_call.id

                yield {
                    "event": "tool_start",
                    "data": {"tool": func_name, "arguments": raw_args}
                }

                try:
                    args_dict = json.loads(raw_args)
                    target_func = TOOL_MAP.get(func_name)
                    if not target_func:
                        raise NotImplementedError(f"未注册的工具函数: {func_name}")

                    # 将 DuckDB 和 AST 解析推入线程池执行，不阻塞异步事件循环
                    tool_output = await asyncio.to_thread(target_func, **args_dict)

                except Exception as e:
                    tool_output = json.dumps({"status": "ERROR", "message": str(e)}, ensure_ascii=False)

                # 将工具执行结果推给前端
                yield {
                    "event": "tool_end",
                    "data": {
                        "tool": func_name,
                        "output": tool_output,
                        "is_error": "SQL_ERROR" in str(tool_output) or "ERROR" in str(tool_output)
                    }
                }

                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": tool_output
                })

        yield {
            "event": "error",
            "data": {"message": "【系统熔断】智能体达到最大轮次上限，停止推理。"}
        }
        yield {"event": "done", "data": {"status": "timeout"}}