import json
from typing import List, Dict, Any
from core.client import get_llm_client
from config import get_settings
from tools.registry import TOOL_MAP, TOOLS_SCHEMA


class AgentEngine:
    def __init__(self, max_turns: int | None = None):
        self.settings = get_settings()
        self.client = get_llm_client()
        self.max_turns = self.settings.max_turns

    def run(self, query: str) -> str:
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "你是一个资深量化投资与财务分析专家，底层对接 DuckDB 分析数据库。\n"
                    "工作准则:\n"
                    "1. 【Schema 先行】: 任何数据查询任务，必须首先调用 get_db_schema 获取物理列与金融计算公式，严禁凭空猜测列名！\n"
                    "2. 【严禁捏造衍生字段】: 数据库中只存储原子财报数据。涉及自由现金流(FCF)、利润率、前瞻增速等派生指标时，必须在 SQL 中按照 Schema 提供的公式现场用算式推导并设置别名 (如 `(cf_ops_ltm_musd + capex_ltm_musd) AS fcf_musd`)。\n"
                    "3. 【严防除零】: 进行除法运算时，分母必须使用 `NULLIF(column, 0)` 规避 ZeroDivision 报错。\n"
                    "4. 【异常自愈】: 若 execute_sql 返回报错报文，仔细阅读错误反馈，修正 SQL 语法或字段后再次调用重试。\n"
                    "5. 【报告交付】: 获取真实数据后，结合半导体产业逻辑输出严谨、专业、带格式化表格的 Markdown 投研简报。"
                )
            },
            {"role": "user", "content": query}
        ]

        for step in range(1, self.max_turns + 1):
            if self.settings.is_debug:
                print(f"\n[状态机轮次: {step}/{self.max_turns}] 发起推理...")

            response = self.client.chat.completions.create(
                model=self.settings.model_name,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.1
            )

            msg = response.choices[0].message
            messages.append(msg)

            # 最终收敛：无需继续调用工具，直接返回研报
            if not msg.tool_calls:
                return msg.content

            # 分发工具调用
            for tool_call in msg.tool_calls:
                func_name = tool_call.function.name
                args_str = tool_call.function.arguments
                call_id = tool_call.id

                print(f"[引擎派发] 执行动作: {func_name} | 参数: {args_str}")

                try:
                    args_dict = json.loads(args_str)
                    target_func = TOOL_MAP.get(func_name)
                    if not target_func:
                        raise NotImplementedError(f"未注册的工具函数: {func_name}")
                    tool_output = target_func(**args_dict)
                except Exception as err:
                    print(f"  [引擎拦截] 工具执行异常: {err}")
                    tool_output = json.dumps({"error": f"系统调度异常: {str(err)}"}, ensure_ascii=False)

                # 将工具执行结果作为事实报文塞回上下文
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": tool_output
                })

            tool_output = target_func(**args_dict)
            if "SQL_ERROR" in str(tool_output) or "error" in str(tool_output):
                print(f"  [工具报错反馈给模型]: {tool_output}")
            else:
                print(f"  [工具执行成功] 数据行已抓取，准备进入下一轮思考。")

        return "【系统熔断】超过最大 ReAct 决策轮次，执行已强制中止。"