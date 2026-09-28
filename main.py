from core.engine import AgentEngine


def main():
    agent = AgentEngine(max_turns=6)

    # 真实的买方半导体投研复合指令
    user_prompt = (
        "请帮我从数据库中筛选出同时满足以下条件的优质标的：\n"
        "1. 市场预期未来一年 EBITDA 增速高于 20%；\n"
        "2. 剔除股权激励(SBC)后的真实自由现金流利润率大于 15%（具备真实造血能力）；\n"
        "3. 产权比率（总负债 / 净资产）低于 40%（资产负债表健康、低杠杆）；\n"
        "输出符合条件标的的股票代码、公司名称、国家、前瞻 EBITDA 增速、真实 FCF 利润率、负债率，"
        "按前瞻 EBITDA 增速从高到低排序，限制前 5 名，并对排名第一的标的的核心基本面给出简要投研点评。"
    )

    print("==================================================")
    print(f"[投研指令下发]:\n{user_prompt}")
    print("==================================================")

    report = agent.run(user_prompt)

    print("\n" + "="*50)
    print(f"[Agent 最终投研报告交付]:\n\n{report}")


if __name__ == "__main__":
    main()