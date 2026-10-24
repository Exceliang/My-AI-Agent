```markdown
# My-AI-Agent: 轻量级金融数据 ReAct 智能体执行引擎

基于原生 Python 状态机与 DeepSeek API 构建的轻量投资分析智能体，结合嵌入式分析型数据库 DuckDB，实现从自然语言指令到结构化行情查询、指标计算与投资决策闭环。

---

## 核心特性

- **零黑盒框架依赖**：剔除 LangChain 等重型抽象库，底层由原生 Python 实现 Thought-Action-Observation 闭环状态机，确保执行链路与 Token 开销的 100% 确定性。
- **Pydantic v2 参数自愈网关**：基于 Pydantic 动态内省导出标准 JSON Schema 工具字典；在入参反序列化阶段精确拦截 `ValidationError`，引导大模型单轮自主修正。
- **高性能嵌入式列存底座**：集成 DuckDB 列式数据库，针对财务流水与行情表提供毫秒级 OLAP 聚合分析，配合 AST 只读语法防御拦截非法写入。
- **FastAPI 异步服务化与 SSE 流式透传**：2.0 版本基于 FastAPI 完成微服务封装，支持通过 `text/event-stream`（SSE）打字机推流实时下发智能体思考中间态与工具执行状态。

---

## 目录结构

```text
My-AI-Agent/
├── core/                  # 调度内核：ReAct 事件循环、状态契约与自愈解析器
├── tools/                 # 物理工具集：DuckDB 财务查询、估值模型与数据计算插件
├── market_data.duckdb     # 本地高性能分析型列式数据库
├── koyfin.json            # 金融终端（Koyfin）指标样例与冷启动数据
├── config.py              # 配置中心：模型入参、API 端点与系统提示词
├── main.py                # 1.0 CLI 终端调试入口
├── server.py              # 2.0 FastAPI 异步 Web 服务入口
├── test.py                # 接口联通性与工具路由单元测试
├── requirements.txt       # 核心运行时依赖清单
└── README.md

```

---

## 快速上手

### 1. 安装依赖

```bash
git clone [https://github.com/Exceliang/My-AI-Agent.git](https://github.com/Exceliang/My-AI-Agent.git)
cd My-AI-Agent
pip install -r requirements.txt

```

### 2. 配置环境变量

在 `config.py` 中配置大模型 API 凭证或设置环境变量：

```bash
export DEEPSEEK_API_KEY="your-api-key"

```

### 3. 本地控制台交互 (CLI 模式)

```bash
python main.py

```

### 4. 启动异步 Web 服务 (FastAPI 模式)

```bash
uvicorn server:app --reload --port 8000

```

* 服务文档地址：`http://127.0.0.1:8000/docs`
* 流式推理接口：`GET /stream` 或 `POST /api/v1/chat`

---

## 演进记录

* **v1.0**：完成本地 DuckDB 挂载、DeepSeek 工具调用与基础 ReAct 命令行闭环。
* **v1.1**：加入 Pydantic v2 强类型入参校验与报错自愈机制，修复 SQL 全表扫描隐患。
* **v2.0**：重构接入 FastAPI 异步框架，支持多连接复用与 SSE 打字机流式输出。

```
