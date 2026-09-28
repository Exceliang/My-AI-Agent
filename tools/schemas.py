from pydantic import BaseModel, Field


class GetSchemaArgs(BaseModel):
    pass


class ExecuteSQLArgs(BaseModel):
    sql_query: str = Field(
        ..., 
        description="待执行的 DuckDB 标准只读 SQL 语句。严禁写 DDL/DML，尽量包含 LIMIT 控制返回条数。"
    )