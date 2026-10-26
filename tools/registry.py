from typing import Any, Callable, Dict, List, Type
from pydantic import BaseModel, ValidationError

from tools.db_tools import execute_sql, get_db_schema
from tools.schemas import ExecuteSQLArgs, GetSchemaArgs

# 1. 参数契约映射表：绑定工具名与对应的 Pydantic 校验模型
TOOL_ARG_MODELS: Dict[str, Type[BaseModel]] = {
    "get_db_schema": GetSchemaArgs,
    "execute_sql": ExecuteSQLArgs,
}

# 2. 底层物理执行算子映射表
RAW_TOOL_MAP: Dict[str, Callable[..., Any]] = {
    "get_db_schema": get_db_schema,
    "execute_sql": execute_sql,
}


def execute_tool_with_validation(func_name: str, **raw_kwargs: Any) -> Any:
    """
    带参数校验与清洗的安全执行网关：
    1. 拦截未注册的非法工具调用
    2. 使用 Pydantic V2 校验大模型生成的入参，提取友好错误信息供 LLM 自愈
    3. 清洗过滤无效冗余字段后，转交底层物理算子执行
    """
    if func_name not in RAW_TOOL_MAP:
        raise NotImplementedError(f"未注册的工具函数: '{func_name}'")

    arg_model = TOOL_ARG_MODELS.get(func_name)
    if arg_model:
        try:
            # 强行按契约模型反序列化与类型转换
            validated = arg_model.model_validate(raw_kwargs)
            clean_kwargs = validated.model_dump()
        except ValidationError as ve:
            # 提取 Pydantic 的定位与提示，转化为 LLM 能看懂的自愈线索
            err_details = "; ".join(
                f"参数 '{'.'.join(str(loc) for loc in err['loc'])}': {err['msg']}"
                for err in ve.errors()
            )
            raise ValueError(f"工具入参格式不合规: {err_details}") from ve
    else:
        clean_kwargs = raw_kwargs

    # 派发给底层物理函数执行
    return RAW_TOOL_MAP[func_name](**clean_kwargs)


def _build_safe_caller(tool_name: str) -> Callable[..., Any]:
    """生成带入参自校验的执行闭包"""
    def caller(**kwargs: Any) -> Any:
        return execute_tool_with_validation(tool_name, **kwargs)
    caller.__name__ = tool_name
    return caller


# 3. 对外暴露的 TOOL_MAP：保持向后兼容，engine.py 直接解包调用即可自动享受参数校验
TOOL_MAP: Dict[str, Callable[..., Any]] = {
    name: _build_safe_caller(name) for name in RAW_TOOL_MAP
}

# 4. OpenAI Function Calling 协议契约矩阵
TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_db_schema",
            "description": "获取数据库的物理表结构、所有可用物理字段及金融派生指标的标准 SQL 计算公式。涉及数据查询前必须先调此工具。",
            "parameters": GetSchemaArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": "在本地 DuckDB 分析引擎中物理执行一条只读 SQL 语句并获取结果集。派生指标需在 SELECT 中由物理字段算式推导。",
            "parameters": ExecuteSQLArgs.model_json_schema(),
        },
    },
]