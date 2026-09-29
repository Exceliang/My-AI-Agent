import json
import httpx

API_URL = "http://127.0.0.1:8000/api/v1/analyze/stream"

query_payload = {
    "query": "从半导体数据库中筛选出前瞻估值偏低、EBITDA增速超20%且资产负债率健康的标的，给出深度分析"
}

print(f"正在建立 SSE 长连接至: {API_URL}\n")

try:
    with httpx.Client(timeout=180.0) as client:
        with client.stream("POST", API_URL, json=query_payload) as response:
            if response.status_code != 200:
                print(f"❌ 连接被拒绝，HTTP 状态码: {response.status_code}")
                print(response.read().decode("utf-8"))
                exit(1)

            event_type = None
            for line in response.iter_lines():
                if not line:
                    continue

                if line.startswith("event:"):
                    event_type = line.replace("event:", "", 1).strip()
                elif line.startswith("data:"):
                    data_str = line.replace("data:", "", 1).strip()
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        data = data_str

                    if event_type == "thought":
                        print(f"\n[思考状态] {data.get('message', data)}")
                    elif event_type == "tool_start":
                        print(f"  ⚡ [执行工具] {data.get('tool')}")
                        if "arguments" in data and "sql_query" in data["arguments"]:
                            print(f"     SQL: {data['arguments']}")
                    elif event_type == "tool_end":
                        status = "❌ 失败" if data.get("is_error") else "✓ 成功"
                        print(f"  {status} [工具返回] 数据已获取")
                    elif event_type == "report":
                        print("\n" + "=" * 50)
                        print("[最终投研交付物]:\n")
                        print(data.get("content", data))
                    elif event_type == "error":
                        print(f"\n❌ [服务端报错]: {data.get('message', data)}")
                    elif event_type == "done":
                        print("\n>>> 流式传输圆满结束。")

except httpx.ConnectError:
    print("❌ 无法连接到服务端，请确认是否已执行 `python server.py`！")
except Exception as e:
    print(f"\n客户端捕获异常: {e}")