import os
import json
from openai import OpenAI
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()
model_name="deepseek-ai/DeepSeek-V4-Flash"
client = OpenAI(
    api_key=os.getenv('API_KEY'),
    base_url=os.getenv('API_URL')
)

# ==========================================
# 1. 本地物理工具实现（加上 **kwargs 防御模型多传参数）
# ==========================================
def get_stock_financials(ticker: str, metric: str, **kwargs) -> str:
    """查询财报指标"""
    print(f"  >>> [工具执行: 财报] 正在查询 {ticker} 的 {metric} ...")
    fake_db = {
        "002594.SZ": {"净利润": "115.8亿元", "毛利率": "21.5%"},
        "TSLA": {"净利润": "21.2亿美元", "毛利率": "17.8%"}
    }
    val = fake_db.get(ticker, {}).get(metric, "数据未收录")
    return json.dumps({"ticker": ticker, "metric": metric, "value": val}, ensure_ascii=False)

def get_price(ticker: str, **kwargs) -> str:
    """查询实时股价（**kwargs 可以吃掉大模型乱传的 metric）"""
    print(f"  >>> [工具执行: 行情] 正在查询 {ticker} 的实时股价 ...")
    fake_prices = {
        "002594.SZ": "285.50元",
        "TSLA": "248.30美元"
    }
    price = fake_prices.get(ticker, "暂无报价")
    return json.dumps({"ticker": ticker, "price": price}, ensure_ascii=False)

# 工具路由字典
TOOL_MAP = {
    "get_stock_financials": get_stock_financials,
    "get_price": get_price
}

# ==========================================
# 2. Schema 菜单定义（明确两者的分工）
# ==========================================
class FinancialArgs(BaseModel):
    ticker: str = Field(..., description="股票代码，如 002594.SZ 或 TSLA")
    metric: str = Field(..., description="要查询的具体财务指标，例如：净利润、毛利率、营业额")

class PriceArgs(BaseModel):
    ticker: str = Field(..., description="股票代码，如 002594.SZ 或 TSLA")

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_financials",
            "description": "【财务分析】用于查询股票的历史财务报表指标，如毛利率、净利润等",
            "parameters": FinancialArgs.model_json_schema()
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_price",
            "description": "【实时行情】仅用于查询股票当前的最新交易价格/股价",
            "parameters": PriceArgs.model_json_schema()
        }
    }
]

# ==========================================
# 3. 真正的 Agent ReAct 闭环循环
# ==========================================
def run_agent(query: str, max_turns: int = 5):
    print(f"\n==========================================")
    print(f"[用户提问]: {query}")
    
    messages = [
        {"role": "system", "content": "你是一个严谨的股票分析助手。请合理使用工具查询真实数据后作答。"},
        {"role": "user", "content": query}
    ]

    # 进入自愈与多轮工具调用的执行循环
    for step in range(max_turns):
        print(f"\n--- [循环第 {step + 1} 轮决策] ---")
        
        # 始终把 tools 传给模型，允许它在任何轮次继续申请工具
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        
        msg = response.choices[0].message
        messages.append(msg)

        # 终止条件：大模型没有再申请调用任何工具，说明它已经拿到了数据，给出了最终自然语言回答
        if not msg.tool_calls:
            print(f"\n[最终结论达成]:\n{msg.content}")
            return

        # 遍历模型在本轮申请调用的所有工具
        for tool_call in msg.tool_calls:
            func_name = tool_call.function.name
            args_str = tool_call.function.arguments
            call_id = tool_call.id

            print(f"[模型申请调用]: {func_name}")
            print(f"[模型提供参数]: {args_str}")

            # 本地物理执行与异常捕获
            try:
                args_dict = json.loads(args_str)
                real_func = TOOL_MAP[func_name]
                # 执行本地函数（**kwargs 保障多余参数不崩溃）
                tool_output = real_func(**args_dict)
                print(f"  [执行成功，获取数据]: {tool_output}")

            except Exception as e:
                # 即使真的发生未预料的严重异常，也作为痛觉反馈塞给模型，让下一轮循环的大模型自愈重试
                print(f"  [执行异常]: {e}")
                tool_output = json.dumps({"error": f"执行失败: {str(e)}，请检查参数后重新尝试"}, ensure_ascii=False)

            # 把工具运行结果（无论是正确数据还是错误信息）追加回上下文
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": tool_output
            })

    print("[熔断]: 超过最大循环轮次，任务中止。")

if __name__ == "__main__":
    run_agent("特斯拉目前的实时股价是多少？")
    run_agent("比亚迪的毛利率是多少？")