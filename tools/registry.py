from tools.schemas import GetSchemaArgs, ExecuteSQLArgs
from tools.db_tools import get_db_schema, execute_sql

TOOL_MAP = {
    "get_db_schema": get_db_schema,
    "execute_sql": execute_sql
}

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_db_schema",
            "description": "获取数据库的物理表结构、所有可用物理字段及金融派生指标的标准 SQL 计算公式。涉及数据查询前必须先调此工具。",
            "parameters": GetSchemaArgs.model_json_schema()
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "在本地 DuckDB 分析引擎中物理执行一条只读 SQL 语句并获取结果集。派生指标需在 SELECT 中由物理字段算式推导。",
            "parameters": ExecuteSQLArgs.model_json_schema()
        }
    }
]