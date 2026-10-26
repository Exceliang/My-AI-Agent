import sqlglot
from pydantic import BaseModel, Field, field_validator
from sqlglot import exp
from sqlglot.errors import ParseError


class GetSchemaArgs(BaseModel):
    """获取数据表物理字段与派生公式的契约模型（无需任何入参）"""
    pass


class ExecuteSQLArgs(BaseModel):
    """执行只读 SQL 查询的契约模型（基于 sqlglot AST 语法树安全沙盒）"""
    sql_query: str = Field(
        ...,
        description=(
            "待执行的 DuckDB 标准只读 SQL 语句。\n"
            "准则:\n"
            "1. 物理表名唯一确定为 `market`；\n"
            "2. 仅允许 SELECT / CTE 只读查询，严禁写操作与系统命令；\n"
            "3. 派生指标需在 SELECT 中由物理字段算式推导，除法必须使用 NULLIF(col, 0) 保护；\n"
            "4. 必须使用 LIMIT 控制返回条数（推荐 LIMIT 20，避免上下文爆炸）。"
        ),
        json_schema_extra={
            "example": (
                "SELECT ticker, name, industry, "
                "round(ebitda_growth_ntm * 100, 2) AS ebitda_growth_pct, "
                "round(roic * 100, 2) AS roic_pct "
                "FROM market "
                "WHERE industry = 'Semiconductors and Semiconductor Equipment' "
                "ORDER BY roic DESC LIMIT 10;"
            )
        }
    )

    @field_validator("sql_query")
    @classmethod
    def validate_readonly_sql(cls, v: str) -> str:
        """
        基于 sqlglot AST 的语义级安全沙盒：
        彻底取代脆弱的正则表达式，实现语法有效性、单语句、只读性与表名四重校验
        """
        cleaned = v.strip().rstrip(";")
        if not cleaned:
            raise ValueError("SQL 查询语句不能为空。")

        # 1. 语法有效性与单语句检查（防止分号注入堆叠语句）
        try:
            expressions = sqlglot.parse(cleaned, read="duckdb")
        except ParseError as pe:
            raise ValueError(f"SQL 语法解析失败 (DuckDB 方言): {str(pe)}") from pe

        if not expressions:
            raise ValueError("未检测到有效的 SQL 语句。")
        if len(expressions) > 1:
            raise ValueError("安全拦截：禁止执行多条分号堆叠语句，仅支持单条只读查询。")

        ast = expressions[0]

        # 2. 根表达式类型校验：只允许 SELECT 或 UNION（支持 WITH ... SELECT 的 CTE 形式）
        if not isinstance(ast, (exp.Select, exp.Union)):
            raise ValueError(
                f"安全拦截：仅允许只读查询，当前根节点为非法操作类型: [{ast.key.upper()}]"
            )

        # 3. 遍历 AST 子树：硬性阻断一切写操作节点与系统/DDL命令
        forbidden_nodes = (
            exp.Create,     # CREATE TABLE ...
            exp.Drop,       # DROP TABLE ...
            exp.Delete,     # DELETE FROM ...
            exp.Insert,     # INSERT INTO ...
            exp.Update,     # UPDATE ...
            exp.Alter,      # ALTER TABLE ...
            exp.Command,    # PRAGMA, SET, ATTACH, DETACH 等管理指令
        )
        for node in ast.find_all(forbidden_nodes):
            raise ValueError(
                f"安全策略拦截：SQL 中检测到高危 AST 语法节点 [{node.key.upper()}]，拒绝执行。"
            )

        # 4. 物理表名白名单校验（提取所有 Table 节点并自动剔除 CTE 别名）
        cte_aliases = {cte.alias_or_name.lower() for cte in ast.ctes}
        for table_node in ast.find_all(exp.Table):
            table_name = table_node.name.lower()
            # 既不是 CTE 内部临时别名，也不是白名单物理表，即刻拦截
            if table_name not in cte_aliases and table_name != "market":
                raise ValueError(
                    f"安全拦截：底层仅开放产业链标的表 `market`，禁止跨表访问 `{table_name}`。"
                )

        return cleaned