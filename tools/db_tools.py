import json
import duckdb
import pandas as pd
import sqlglot
from sqlglot import exp

DB_PATH = "market_data.duckdb"
ALLOWED_TABLES = {"market"}
MAX_LIMIT = 30


def get_db_schema(**kwargs) -> str:
    """
    提供数据库的真实物理字段与金融指标的 SQL 推导规范
    """
    schema_doc = """
【不可变的物理列清单】:
- ticker (VARCHAR): 股票代码 (如 NVDA, A005930, 7735)
- company_name (VARCHAR): 公司英文全称
- country (VARCHAR): 注册国家/地区二字码 (US, KR, JP 等)
- sector (VARCHAR): 行业大类
- industry (VARCHAR): 细分行业
- currency (VARCHAR): 原生报表计价货币
- current_price (DOUBLE): 最新股价
- market_cap_musd (DOUBLE): 总市值 (单位: 百万美元)
- enterprise_value_musd (DOUBLE): 企业价值 EV (单位: 百万美元)
- ev_ebitda_rank_pct (DOUBLE): 行业内 EV/EBITDA 估值分位数 (0~100)

【历史真实财务字段 (近12个月 LTM, 单位: 百万美元)】:
- revenue_ltm_musd (DOUBLE): 营业总收入
- ebit_ltm_musd (DOUBLE): 息税前利润 EBIT
- ebitda_ltm_musd (DOUBLE): 核心 EBITDA
- cf_ops_ltm_musd (DOUBLE): 经营活动现金流
- capex_ltm_musd (DOUBLE): 资本开支 (原始报表记为负值，如 -7354)
- sbc_ltm_musd (DOUBLE): 股权激励支出 Stock-Based Comp
- tax_ltm_musd (DOUBLE): 所得税支出

【负债与股东权益 (单位: 百万美元)】:
- total_equity_musd (DOUBLE): 股东权益/净资产
- total_debt_musd (DOUBLE): 总有息负债 (长期负债 + 一年内到期负债 + 融资租赁)

【华尔街一致预期 (Consensus Estimates, 单位: 百万美元)】:
- act_sales_annual_musd (DOUBLE): 上财年结算实际年营收
- act_ebitda_annual_musd (DOUBLE): 上财年结算实际年 EBITDA
- est_sales_fy0_musd (DOUBLE): 分析师一致预期下一财年年营收
- est_ebitda_fy0_musd (DOUBLE): 分析师一致预期下一财年年 EBITDA
- est_ebitda_fy1_musd (DOUBLE): 分析师一致预期下下财年年 EBITDA
- est_ebitda_3m_fy0_musd (DOUBLE): 3个月前分析师对下财年的 EBITDA 预期
- est_ebitda_ntm_musd (DOUBLE): 华尔街一致预期未来12个月 EBITDA (NTM)

【金融派生指标 SQL 编写算式规范】:
* 本表不存预计算字段，派生指标必须在 SQL 中使用物理列自行推导：
1. 真实自由现金流 (FCF):
   `round(cf_ops_ltm_musd + capex_ltm_musd, 2)`
2. 剔除 SBC 的真实自由现金流:
   `round((cf_ops_ltm_musd + capex_ltm_musd) - COALESCE(sbc_ltm_musd, 0), 2)`
3. 剔除 SBC 后的自由现金流利润率 (%):
   `round((((cf_ops_ltm_musd + capex_ltm_musd) - COALESCE(sbc_ltm_musd, 0)) / NULLIF(revenue_ltm_musd, 0)) * 100, 2)`
4. 未来12个月前瞻 EBITDA 增速 (%):
   `round(((est_ebitda_ntm_musd - ebitda_ltm_musd) / NULLIF(ebitda_ltm_musd, 0)) * 100, 2)`
5. 分析师 3 个月预期修正动量 (%):
   `round(((est_ebitda_fy0_musd - est_ebitda_3m_fy0_musd) / NULLIF(est_ebitda_3m_fy0_musd, 0)) * 100, 2)`
6. 产权比率 / 负债率 (%):
   `round((total_debt_musd / NULLIF(total_equity_musd, 0)) * 100, 2)`
7. EV/EBITDA 估值倍数:
   `round(enterprise_value_musd / NULLIF(ebitda_ltm_musd, 0), 2)`

【查询防御要求】:
- 分母可能为 0 时务必包裹 `NULLIF(col, 0)`；
- 过滤条件使用 `IS NOT NULL` 规避空值。
"""
    return schema_doc.strip()


def validate_and_sanitize_sql(sql_str: str) -> str:
    """
    通过 sqlglot AST 语法树编译器进行安全断言与动态重写 (修复类型注水 Bug)
    """
    try:
        parsed_statements = sqlglot.parse(sql_str, read="duckdb")
    except Exception as parse_err:
        raise ValueError(f"SQL 语法解析异常: {str(parse_err)}")

    if len(parsed_statements) != 1 or parsed_statements[0] is None:
        raise ValueError("安全拦截: 仅允许执行单条 SQL 语句，严禁堆叠查询。")

    ast = parsed_statements[0]

    # 1. 严格断言只读类型
    if not isinstance(ast, exp.Select):
        raise ValueError("安全拦截: 非法操作类型，仅允许执行 SELECT 查询。")

    # 2. 表名白名单判定
    for table in ast.find_all(exp.Table):
        table_name = table.name.lower()
        if table_name not in ALLOWED_TABLES:
            raise ValueError(f"安全拦截: 目标表 `{table_name}` 未在白名单中，仅允许访问: {ALLOWED_TABLES}")

    # 3. 安全替换 LIMIT：使用标准的 Literal.number 节点，避免类型错误
    limit_node = ast.find(exp.Limit)
    if limit_node is None:
        ast = ast.limit(MAX_LIMIT)
    else:
        try:
            curr_limit = int(limit_node.expression.this)
            if curr_limit > MAX_LIMIT:
                # 修复核心：必须用 exp.Literal.number 包装字符串
                limit_node.set("expression", exp.Literal.number(str(MAX_LIMIT)))
        except Exception:
            ast = ast.limit(MAX_LIMIT)

    return ast.sql(dialect="duckdb")


def execute_sql(sql_query: str, **kwargs) -> str:
    """
    在 DuckDB 中执行 SQL 并将数据以 Markdown 格式返回
    """
    sql_query = sql_query.strip().strip("'\"\\").strip()
    if sql_query.endswith(";"):
        sql_query = sql_query[:-1].strip()
    
    print(f"\n  >>> [AST 审计审查] 收到输入 SQL:\n      {sql_query}")
    
    try:
        safe_sql = validate_and_sanitize_sql(sql_query)
        print(f"  >>> [AST 编译通过] 下推安全 SQL:\n      {safe_sql}\n")

        conn = duckdb.connect(DB_PATH, read_only=True)
        df: pd.DataFrame = conn.execute(safe_sql).df()
        conn.close()

        if df.empty:
            return json.dumps({"message": "查询执行成功，但返回数据为空（无匹配记录）。"}, ensure_ascii=False)

        return df.to_markdown(index=False)

    except Exception as e:
        # 将结构化错误信息返回给 Agent，驱动 ReAct 自愈重写
        return json.dumps({
            "status": "SQL_ERROR",
            "message": str(e),
            "hint": "请根据 get_db_schema 中的物理列名检查字段拼写，派生指标请使用原生加减乘除计算。"
        }, ensure_ascii=False)