import duckdb
import pandas as pd

print("[1/2] 正在构建高保真金融量化核心因子数据集...")

# 采用真实科技巨头与半导体龙头近期财务数据作为基准底表
raw_data = [
    {
        "ticker": "NVDA",
        "company_name": "NVIDIA Corporation",
        "sector": "Technology",
        "industry": "Semiconductors",
        "market_cap": 3150000000000,
        "pe_ratio": 54.2,
        "forward_pe": 32.5,
        "ev_to_ebitda": 42.1,
        "roic": 0.584,          # 58.4%
        "gross_margin": 0.751,   # 75.1%
        "fcf": 27000000000,      # 27B
        "revenue": 60920000000,
        "current_price": 128.50
    },
    {
        "ticker": "TSLA",
        "company_name": "Tesla, Inc.",
        "sector": "Consumer Cyclical",
        "industry": "Auto Manufacturers",
        "market_cap": 780000000000,
        "pe_ratio": 65.8,
        "forward_pe": 58.2,
        "ev_to_ebitda": 38.6,
        "roic": 0.128,          # 12.8%
        "gross_margin": 0.179,   # 17.9%
        "fcf": 3200000000,       # 3.2B
        "revenue": 96770000000,
        "current_price": 248.30
    },
    {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "market_cap": 3450000000000,
        "pe_ratio": 33.6,
        "forward_pe": 28.9,
        "ev_to_ebitda": 24.3,
        "roic": 0.521,          # 52.1%
        "gross_margin": 0.462,   # 46.2%
        "fcf": 108800000000,     # 108.8B
        "revenue": 385600000000,
        "current_price": 227.40
    },
    {
        "ticker": "MSFT",
        "company_name": "Microsoft Corporation",
        "sector": "Technology",
        "industry": "Software - Infrastructure",
        "market_cap": 3200000000000,
        "pe_ratio": 35.8,
        "forward_pe": 30.1,
        "ev_to_ebitda": 22.8,
        "roic": 0.286,          # 28.6%
        "gross_margin": 0.698,   # 69.8%
        "fcf": 74070000000,      # 74.07B
        "revenue": 245120000000,
        "current_price": 430.20
    },
    {
        "ticker": "GOOGL",
        "company_name": "Alphabet Inc.",
        "sector": "Communication Services",
        "industry": "Internet Content & Information",
        "market_cap": 2050000000000,
        "pe_ratio": 24.1,
        "forward_pe": 20.4,
        "ev_to_ebitda": 15.6,
        "roic": 0.264,          # 26.4%
        "gross_margin": 0.575,   # 57.5%
        "fcf": 69400000000,      # 69.4B
        "revenue": 307390000000,
        "current_price": 165.80
    }
]

df_stocks = pd.DataFrame(raw_data)

print("[2/2] 正在落盘写入 DuckDB 单文件数据库...")
conn = duckdb.connect("market_data.duckdb")

# 写入物理表
conn.execute("CREATE OR REPLACE TABLE stock_fundamentals AS SELECT * FROM df_stocks")
print("  ✓ 数据表 `stock_fundamentals` 写入完成！")

# 检验表结构与数据条数
count = conn.execute("SELECT count(*) FROM stock_fundamentals").fetchone()[0]
print(f"  ✓ 数据库中现有记录数: {count}")

print("\n--- 采样检验 (ROIC 与 自由现金流 FCF 排序) ---")
query_sample = """
SELECT 
    ticker, 
    company_name, 
    round(roic * 100, 1) || '%' AS roic, 
    round(gross_margin * 100, 1) || '%' AS gross_margin,
    round(fcf / 1e9, 1) || 'B' AS fcf_billion
FROM stock_fundamentals 
ORDER BY roic DESC;
"""
print(conn.execute(query_sample).df().to_string())

conn.close()