import json
import duckdb
import pandas as pd
from pathlib import Path


def init_database(json_filename: str = "koyfin.json", db_path: str = "market_data.duckdb"):
    file_path = Path(json_filename)

    print(f"[1/4] 正在加载并递归扫描文件: {file_path.name} ...")
    with open(file_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # 递归提取所有股票实体节点
    equity_items = []
    def extract_equities(node):
        if isinstance(node, dict):
            if "t_n" in node and ("t" in node or "t_id" in node):
                equity_items.append(node)
            else:
                for child in node.values():
                    extract_equities(child)
        elif isinstance(node, list):
            for child in node:
                extract_equities(child)

    extract_equities(raw_data)
    print(f"  ✓ 成功定位到 {len(equity_items)} 家公司记录")

    if not equity_items:
        raise ValueError("未在 JSON 中找到股票实体节点，请确认输入数据。")

    # 安全提取 value 的闭包函数
    def get_num(item: dict, *keys) -> float | None:
        """按顺序尝试读取 key，只提取其中的真实数值"""
        for k in keys:
            obj = item.get(k)
            if isinstance(obj, dict):
                val = obj.get("value")
                if val is not None:
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        pass
            elif isinstance(obj, (int, float)):
                return float(obj)
        return None

    rows = []
    for item in equity_items:
        # 1. 基础标识与分类
        ticker = item.get("t") or item.get("t_id", "UNKNOWN")
        name = item.get("t_n", "UNKNOWN")
        country = item.get("company_country", "Unknown")
        sector = item.get("t_sec", "Unknown")
        industry = item.get("t_ind", "Unknown")
        currency = item.get("t_u", "USD")

        # 2. 真实存在的行情与估值
        price = get_num(item, "p_l")
        mkt_cap = get_num(item, "f_mkt")
        ev = get_num(item, "f_ev")
        ev_ebitda_rank = get_num(item, "evebitda_gs_pr")

        # 3. 真实存在的历史财务核心项目 (LTM, 单位百万美元)
        revenue_ltm = get_num(item, "f_r-LTM")
        ebit_ltm = get_num(item, "f_ebit-LTM", "f_ebit")
        ebitda_ltm = get_num(item, "f_ebitda_incl-LTM")
        cf_ltm = get_num(item, "f_cf-LTM")
        capex_ltm = get_num(item, "f_capex-LTM")
        sbc_ltm = get_num(item, "f_stkcomp-LTM") or 0.0
        tax_ltm = get_num(item, "f_tax-LTM", "f_tax")

        # 4. 真实存在的资本结构与负债项目
        total_equity = get_num(item, "f_toteq", "f_toteq-quarterly", "f_toteq_rp_fq0")
        lt_debt = get_num(item, "f_ltdebt", "f_ltdebt-quarterly", "f_ltdebt_rp_fq0") or 0.0
        cur_debt = get_num(item, "f_curpordeb", "f_curpordeb-quarterly", "f_curpordeb_rp_fq0") or 0.0
        cap_leases = get_num(item, "f_capleas", "f_capleas-quarterly", "f_capleas_rp_fq0") or 0.0
        cur_leases = get_num(item, "f_curporlea", "f_curporlea-quarterly", "f_curporlea_rp_fq0") or 0.0

        # 5. 真实存在的华尔街一致预期 (Consensus Estimates)
        act_sales_annual = get_num(item, "fest_actsales-annual")
        act_ebitda_annual = get_num(item, "fest_actebitda-annual")
        est_sales_fy0 = get_num(item, "fest_estsales_rp_fy0")
        est_ebitda_fy0 = get_num(item, "fest_estebitda_rp_fy0")
        est_ebitda_fy1 = get_num(item, "fest_estebitda_rp_fy1")
        est_ebitda_3m_fy0 = get_num(item, "fest_estebitda_3m_rp_fy0")
        est_ebitda_ntm = get_num(item, "fest_estebitda_ntm")

        rows.append({
            "ticker": ticker,
            "company_name": name,
            "country": country,
            "sector": sector,
            "industry": industry,
            "currency": currency,
            "current_price": price,
            "market_cap_musd": mkt_cap,
            "enterprise_value_musd": ev,
            "ev_ebitda_rank_pct": round(ev_ebitda_rank * 100, 1) if ev_ebitda_rank is not None else None,
            "revenue_ltm_musd": revenue_ltm,
            "ebit_ltm_musd": ebit_ltm,
            "ebitda_ltm_musd": ebitda_ltm,
            "cf_ops_ltm_musd": cf_ltm,
            "capex_ltm_musd": capex_ltm,
            "sbc_ltm_musd": sbc_ltm,
            "tax_ltm_musd": tax_ltm,
            "total_equity_musd": total_equity,
            "total_debt_musd": round(lt_debt + cur_debt + cap_leases + cur_leases, 2),
            "act_sales_annual_musd": act_sales_annual,
            "act_ebitda_annual_musd": act_ebitda_annual,
            "est_sales_fy0_musd": est_sales_fy0,
            "est_ebitda_fy0_musd": est_ebitda_fy0,
            "est_ebitda_fy1_musd": est_ebitda_fy1,
            "est_ebitda_3m_fy0_musd": est_ebitda_3m_fy0,
            "est_ebitda_ntm_musd": est_ebitda_ntm
        })

    df = pd.DataFrame(rows)

    print("\n[2/4] 真实字段数据质量审计（非空数据行数统计）：")
    coverage = df.notnull().sum()
    for col, count in coverage.items():
        print(f"  - {col:<26}: {count}/{len(df)} 覆盖")

    print("\n[3/4] 正在将真实结构写入 DuckDB 数据库...")
    conn = duckdb.connect(db_path)
    conn.execute("CREATE OR REPLACE TABLE market AS SELECT * FROM df")
    total_count = conn.execute("SELECT count(*) FROM market").fetchone()[0]
    print(f"  ✓ 数据库写入成功！总行数: {total_count}")

    print("\n[4/4] 真实数据多因子验证查询（通过原生字段在 SQL 里直接计算 FCF 与增速）：")
    test_sql = """
    SELECT 
        ticker,
        company_name,
        country,
        market_cap_musd,
        round(cf_ops_ltm_musd + capex_ltm_musd, 1) AS fcf_musd,
        round(((est_ebitda_ntm_musd - ebitda_ltm_musd) / ebitda_ltm_musd) * 100, 1) || '%' AS ntm_growth,
        round((total_debt_musd / total_equity_musd) * 100, 1) || '%' AS d_e_ratio
    FROM market
    WHERE cf_ops_ltm_musd IS NOT NULL 
      AND capex_ltm_musd IS NOT NULL
      AND est_ebitda_ntm_musd IS NOT NULL
      AND total_equity_musd > 0
    ORDER BY (cf_ops_ltm_musd + capex_ltm_musd) DESC
    LIMIT 5;
    """
    print(conn.execute(test_sql).df().to_string())
    conn.close()


if __name__ == "__main__":
    init_database()