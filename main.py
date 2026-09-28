from core.engine import AgentEngine


def main():
    agent = AgentEngine(max_turns=6)

    # 真实的买方半导体投研复合指令
    user_prompt = (
        "请帮我从 market_data.duckdb 数据库中筛选出同时满足以下条件的优质标的：\n"
        "1. 行业为Semiconductors and Semiconductor Equipments；\n"
        "2. 前瞻估值不能太高；\n"
        "3. 尽量选一个EBITDA增速和roic双高的；\n"
        "输出符合条件标的的股票代码、公司名称、国家、前瞻 EBITDA 增速、真实 FCF 利润率、负债率，"
        "对标的的核心基本面给出简要投研点评。"
    )

    print("==================================================")
    print(f"[投研指令下发]:\n{user_prompt}")
    print("==================================================")

    report = agent.run(user_prompt)

    print("\n" + "="*50)
    print(f"[Agent 最终投研报告交付]:\n\n{report}")


if __name__ == "__main__":
    main()