import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List

from config import get_settings
from core.client import get_async_llm_client, get_llm_client
from tools.registry import TOOL_MAP, TOOLS_SCHEMA


class AgentEngine:
    def __init__(self, max_turns: int | None = None, max_output_chars: int = 4000):
        self.settings = get_settings()
        self.client = get_llm_client()
        self.async_client = get_async_llm_client()
        self.max_turns = max_turns or 10
        # 防爆限额：单个工具结果最大字符数，超出强制截断以保护 Context Window
        self.max_output_chars = max_output_chars

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

    def _safe_serialize_output(self, raw_output: Any) -> str:
        """
        数据序列化与上下文截断熔断器：
        1. 确保写入 messages['content'] 的值必须为标准 str（满足 OpenAI 协议契约）
        2. 防止 SQL 查询出海量数据直接击穿上下文窗口
        """
        if isinstance(raw_output, str):
            text = raw_output
        else:
            try:
                text = json.dumps(raw_output, ensure_ascii=False)
            except Exception:
                text = str(raw_output)

        if len(text) > self.max_output_chars:
            half = self.max_output_chars // 2
            warning_msg = (
                f"\n\n... [数据量过大触发防御性截断：原始长度 {len(text)} 字符，已保留前后关键字段。"
                f"请在 SQL 中添加 LIMIT 或更严苛的过滤条件] ...\n\n"
            )
            return text[:half] + warning_msg + text[-half:]
        return text

    def _execute_tool_sync(self, func_name: str, args_str: str) -> str:
        """同步执行单个工具函数"""
        try:
            args_dict = json.loads(args_str)
            target_func = TOOL_MAP.get(func_name)
            if not target_func:
                raise NotImplementedError(f"未注册工具: {func_name}")
            raw_result = target_func(**args_dict)
        except Exception as err:
            raw_result = {"status": "ERROR", "message": f"系统调度异常: {str(err)}"}
        return self._safe_serialize_output(raw_result)

    async def _execute_tool_async(self, func_name: str, args_str: str) -> str:
        """异步执行单个工具函数（将阻塞调用分发到底层线程池）"""
        try:
            args_dict = json.loads(args_str)
            target_func = TOOL_MAP.get(func_name)
            if not target_func:
                raise NotImplementedError(f"未注册的工具函数: {func_name}")
            # DuckDB 查询和 AST 解析放入线程池，防止挂起异步事件循环
            raw_result = await asyncio.to_thread(target_func, **args_dict)
        except Exception as err:
            raw_result = {"status": "ERROR", "message": f"工具执行异常: {str(err)}"}
        return self._safe_serialize_output(raw_result)

    # ==================== 1. CLI 同步运行入口 ====================
    def run(self, query: str) -> str:
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": query}
        ]

        for _ in range(1, self.max_turns + 1):
            response = self.client.chat.completions.create(
                model=self.settings.model_name,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.1
            )
            msg = response.choices[0].message
            # 统一转为标准字典存入上下文，防止 SDK 模型对象在序列化时产生格式脱节
            messages.append(msg.model_dump(exclude_none=True))

            # 决策完成，输出最终研报
            if not msg.tool_calls:
                return msg.content or "未生成有效研报"

            # 遍历执行工具调用
            for tool_call in msg.tool_calls:
                func_name = tool_call.function.name
                args_str = tool_call.function.arguments
                call_id = tool_call.id

                tool_output = self._execute_tool_sync(func_name, args_str)

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
            yield {
                "event": "thought",
                "data": {"turn": turn, "message": f"正在进行第 {turn}/{self.max_turns} 轮分析决策..."}
            }

            response = await self.async_client.chat.completions.create(
                model=self.settings.model_name,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.1
            )
            msg = response.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))

            # 无工具调用，交付终局研报
            if not msg.tool_calls:
                yield {
                    "event": "report",
                    "data": {"content": msg.content or "未生成有效研报"}
                }
                yield {"event": "done", "data": {"status": "success"}}
                return

            # 并发执行准备：先向前端批量推送 tool_start 状态
            tool_tasks = []
            for tool_call in msg.tool_calls:
                func_name = tool_call.function.name
                raw_args = tool_call.function.arguments

                yield {
                    "event": "tool_start",
                    "data": {"tool": func_name, "arguments": raw_args}
                }
                # 挂载并发任务
                tool_tasks.append(self._execute_tool_async(func_name, raw_args))

            # 核心优化：利用 asyncio.gather 并发执行本轮产生的所有工具调用
            tool_outputs = await asyncio.gather(*tool_tasks)

            # 统一回传事件并挂载上下文
            for tool_call, tool_output in zip(msg.tool_calls, tool_outputs):
                yield {
                    "event": "tool_end",
                    "data": {
                        "tool": tool_call.function.name,
                        "output": tool_output,
                        "is_error": "ERROR" in tool_output or "SQL_ERROR" in tool_output
                    }
                }

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_output
                })

        yield {
            "event": "error",
            "data": {"message": "【系统熔断】智能体达到最大轮次上限，停止推理。"}
        }
        yield {"event": "done", "data": {"status": "timeout"}}