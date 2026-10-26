import argparse
import json
import sys
import httpx

API_URL = "http://127.0.0.1:8000/api/v1/analyze/stream"
DEFAULT_QUERY = (
    "从半导体数据库中筛选出前瞻估值偏低、EBITDA增速超20%且资产负债率健康的标的，"
    "给出深度分析"
)


def dispatch_sse_event(event_type: str, raw_data_str: str) -> None:
    """标准 SSE 事件分发器"""
    try:
        data = json.loads(raw_data_str)
    except json.JSONDecodeError:
        data = raw_data_str

    if event_type == "thought":
        msg = data.get("message", data) if isinstance(data, dict) else data
        print(f"\n[思考状态] {msg}")

    elif event_type == "tool_start":
        tool_name = data.get("tool", "unknown") if isinstance(data, dict) else "unknown"
        print(f"  ⚡ [执行工具] {tool_name}")

        raw_args = data.get("arguments", "") if isinstance(data, dict) else ""
        if isinstance(raw_args, str):
            try:
                parsed_args = json.loads(raw_args)
            except Exception:
                parsed_args = raw_args
        else:
            parsed_args = raw_args

        if isinstance(parsed_args, dict) and "sql_query" in parsed_args:
            sql_clean = parsed_args["sql_query"].strip().replace("\n", " ")
            print(f"     SQL: {sql_clean}")
        elif parsed_args:
            print(f"     入参: {parsed_args}")

    elif event_type == "tool_end":
        is_error = data.get("is_error", False) if isinstance(data, dict) else False
        status = "❌ 执行报错" if is_error else "✓ 成功返回"
        print(f"  {status} [工具返回数据已就绪]")

    elif event_type == "report":
        content = data.get("content", data) if isinstance(data, dict) else data
        print("\n" + "=" * 55)
        print("[最终投研交付物]:\n")
        print(content)

    elif event_type == "error":
        err_msg = data.get("message", data) if isinstance(data, dict) else data
        print(f"\n❌ [服务端异常]: {err_msg}")

    elif event_type == "done":
        status = data.get("status", "success") if isinstance(data, dict) else "success"
        print(f"\n>>> 流式传输圆满结束 (状态: {status})。")


def run_stream_test(query: str, abort_test: bool = False) -> None:
    """
    运行流式集成测试
    :param query: 投研指令
    :param abort_test: 是否模拟中途主动断开，用于测试服务端的 is_disconnected() 熔断逻辑
    """
    print(f"正在建立 SSE 长连接至: {API_URL}")
    print(f"指令内容: {query}\n" + "-" * 55)

    # 细粒度超时控制：连接超时 5s（快速探测服务端是否存活），读取超时 180s（容纳深度推理）
    timeout_cfg = httpx.Timeout(timeout=180.0, connect=5.0)

    try:
        with httpx.Client(timeout=timeout_cfg) as client:
            with client.stream("POST", API_URL, json={"query": query}) as response:
                if response.status_code != 200:
                    print(f"❌ 连接被拒绝，HTTP 状态码: {response.status_code}")
                    print(response.read().decode("utf-8"))
                    sys.exit(1)

                event_type = "message"
                data_lines: list[str] = []

                # 标准 W3C SSE 逐行状态机消费
                for line in response.iter_lines():
                    # 遇到空行意味着一条完整的 SSE 帧结束（\n\n）
                    if not line:
                        if data_lines:
                            raw_payload = "\n".join(data_lines)
                            dispatch_sse_event(event_type, raw_payload)

                            # 若开启断连模拟，在触发首个工具时主动掐断连接
                            if abort_test and event_type == "tool_start":
                                print("\n⚠️ [断连测试触发] 客户端已主动断开 TCP 连接，请查看服务端控制台验证是否触发熔断！")
                                break

                            # 重置帧缓冲区
                            event_type = "message"
                            data_lines = []
                        continue

                    if line.startswith("event:"):
                        event_type = line.replace("event:", "", 1).strip()
                    elif line.startswith("data:"):
                        data_lines.append(line.replace("data:", "", 1).strip())

    except httpx.ConnectError:
        print("\n❌ 无法连接到服务端，请确认是否已执行 `python server.py`！")
    except httpx.ReadTimeout:
        print("\n❌ 请求读取超时：服务端在 180 秒内未完成多步推理，请检查模型响应。")
    except Exception as e:
        print(f"\n客户端运行时捕获异常: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Investment Analysis Agent SSE 集成测试客户端")
    parser.add_argument("query", nargs="?", default=DEFAULT_QUERY, help="投研自然语言查询文本")
    parser.add_argument("--abort", action="store_true", help="模拟中途强退断连，测试服务端 Token 熔断感知机制")
    args = parser.parse_args()

    run_stream_test(query=args.query, abort_test=args.abort)