# 技术依赖与本体能力对照（迭代 1）

结论：这套选型适合“业务本体应用平台”，但安装或调用全部依赖，并不自动成为完整的 OWL/SWRL 标准本体推理系统。当前核心仍是关系数据库中的对象、关系、映射和规则，以及 AI 辅助生成。应围绕业务链路补齐能力，再按需要增加标准语义引擎。

以下为代码调用点检查；“已调用”不表示生产服务连接或业务能力已全面验收。

| 原 requirements.txt 依赖 | 能力与本项目用途 | 代码现状 / 本轮决定 |
|---|---|---|
| fastapi | HTTP API、路由、依赖注入 | 广泛用于 app/api；保留 |
| uvicorn[standard] | ASGI 服务进程 | Docker 启动后端；保留 |
| sqlalchemy | ORM、事务和数据库访问 | 存储对象、属性、关系、技能、草稿；保留 |
| alembic | 数据库版本迁移 | 原项目主要 create_all/启动时 ALTER；本轮建立新增草稿表迁移，旧表迁移后续收敛 |
| psycopg2-binary | PostgreSQL 驱动 | connectors/postgresql.py；保留，真实连接需专项测试 |
| pydantic | 请求结构、类型校验 | schemas；新增 AI 草稿结构及引用校验，不能替代业务推理 |
| pydantic-settings | 环境变量配置 | app/config.py；保留 |
| python-jose[cryptography] | JWT 签发与校验 | core/security.py；保留 |
| passlib[bcrypt] | 密码哈希封装 | 未找到实际导入，已有直接 bcrypt 实现；本轮移除 |
| bcrypt | 密码哈希与核验 | core/security.py；保留 |
| python-multipart | 表单与文件上传解析 | 上传文档/数据接口；保留 |
| redis | 缓存、锁、消息等能力 | 当前确认调用主要是监控连接检查，尚不能声称已有 Redis 任务队列 |
| openai | OpenAI 兼容模型客户端 | llm_resolver、建模、智能体；可调用兼容的 DeepSeek 接口；锁定已验收版本 |
| httpx | HTTP/异步 HTTP 客户端 | 模型通信及外部工具请求；锁定已验收版本 |
| neo4j | 属性图数据库驱动 | 当前确认调用为监控检查；尚非本体运行存储引擎，更不等同 OWL 推理器 |
| rdflib | RDF 图与 RDF/OWL 文件解析 | file_import.py 有部分 OWL/RDF 导入；尚无完整 OWL 语义一致性推理 |
| boto3 | S3 兼容对象存储客户端 | S3/MinIO 文档、连接器、存储服务；保留 |
| python-docx | Word 文档读取 | 文档建模、数据资产解析；保留 |
| pdfplumber | PDF 文本/表格提取 | 文档解析；不代表已经具备扫描件 OCR |
| openpyxl | Excel 读写 | 文档及资产读取；保留 |
| pandas | 表格数据处理 | builder.py 的表格导入；保留，不能替代完整调度/ETL 引擎 |
| sqlglot | SQL 解析与方言分析 | data_plane/sql_introspect.py；保留并锁版本；不属于本体语义推理 |
| sse-starlette | SSE 事件流 | data_plane/events.py；保留并锁版本 |
| psutil | CPU/内存/进程指标 | 监控 API/collector；保留 |

补齐的漏项：`PyMySQL`（MySQL 连接器已有延迟导入）、`python-pptx`（doc_builder.py 已有 PPTX 解析）。本轮验证包安装和导入；尚未在外部 MySQL 生产库做连接测试。

## 如何与迭代结合

| 业务步骤 | 当前技术基础 | 计划验收能力 |
|---|---|---|
| 需求分析 | FastAPI + Pydantic + 模型客户端 | 场景描述、待澄清问题、AI 草稿预览 |
| 数据源表 | SQLAlchemy + 各数据库驱动 + 文件解析 | 真实连接、元数据和样例读取 |
| 数据处理 | 已有数据管道 + SQLGlot | 字段清洗、关联及质量检查可追溯 |
| 子图建模 | 数据库对象模型 + AI + 表单 | 同一草稿、复用对象、通用/业务规则人工审核 |
| 本体库 | 当前 SQLAlchemy + 版本模型；RDFLib 部分导入 | 映射真实数据、版本发布、规则运行边界；后续评估 SHACL |
| 本体应用 | 已有技能服务 + 智能体工具调用 | 问答调用已发布技能，返回数据来源与运行记录 |

本轮规则是受限的声明式数据约束，支持必填、比较和集合成员；它不是 SWRL，也不提供 OWL 推理完备性。需要标准交换/一致性验证时，再验证 RDF/OWL 导出、SHACL 验证与适合的推理器，而不是为了“用完依赖”引入额外服务。

## 兼容与迁移边界

- 已锁定本机回归验证过的 OpenAI、HTTPX、RDFLib、SQLGlot 和 SSE 版本；尚未实现全量含哈希锁文件。
- Alembic 本轮只管理 `modeling_drafts`、`modeling_draft_events`，并保留旧表启动兼容逻辑。新库、已有库、重复升级已测试；PostgreSQL 迁移尚待专项验收。
- 本体草稿是 SQLite/配置数据库持久化数据，不依赖浏览器缓存。审核记录保存版本号和审核者。
- 新增规则目前以 draft 状态进入规则管理，真实数据启用留待下一版；接口显式阻止把样例测试当业务执行成功。
- 本轮同时修复管理员启动时被重置密码的问题；新建测试库支持 `BOOTSTRAP_ADMIN_PASSWORD`，已有用户密码保持不变。
