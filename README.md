<div align="center">

# 知彼 Ontology

**企业级本体智能平台**

*本体驱动 · 语义织网 · 让数据可理解 · 让 AI 可信赖*

**[中文](README.md)** | **[English](README.en.md)**

[![Vue 3](https://img.shields.io/badge/Vue-3.5-4FC08D?logo=vue.js)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![TypeScript](https://img.shields.io/badge/TypeScript-6.x-3178C6?logo=typescript)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 项目简介

知彼 Ontology 把散落在各业务系统里的数据，收敛成一套**可查询、可推理、可执行**的业务本体，并让智能应用直接建立在这套语义之上。平台不是又一个 BI 或数据目录，它解决的是"AI 拿到的业务语义不可控"这件事：数据接入之后先建模成本体对象、属性、关系与规则，再由本体对外提供查询与行动接口，Agent 只能通过这套受控接口取数、判断、执行，全过程留痕。

一条主线贯穿全平台：**接入数据 → 构建本体 → 发布语义 → 装配逻辑与技能 → 交付业务应用 → 场景运行与追踪**。平台为此提供六个业务域和一条六步交付闭环，团队从需求到可运行的业务应用不需要写胶水代码，也不需要让模型直接生成 SQL。

### 核心亮点

- **六步业务交付闭环** — 需求分析 → 数据源表 → 数据处理 → 子图建模 → 本体库 → 本体应用，每一步自动校验链路是否真的通，最后在项目工作区里直接查对象、执行行动
- **五种本体建模入口** — 手动构建、AI/表单建模（草稿可持久化、多人不互相覆盖）、模板构建、文档抽取、资产对话式构建，覆盖从零到一和从存量数据反推
- **受控的 AI 问答** — Agent 只能调用注册的只读技能，模型不生成 SQL；技能白名单、首轮强制工具调用、全链路 `AgentTrace` 与 Token 统计
- **发布即验证** — 草稿 → 审核 → 注水 → 发布四步流水线，配 7 项质量门禁与四阶段水合验证，发布前就用真实数据把映射跑一遍
- **可复用的演示与样例** — 内置客户演示包与四组非军事验收样例（慢病、文献、BIM、供应链），一条命令幂等安装，不覆盖已有数据与密钥
- **双流水线交付** — Gitee Go 与 GitHub Actions 共用文件锁，同一台 ECS 上互不踩踏，构建失败不动线上容器

---

## 平台全景

产品按六个业务域组织导航（见 `frontend/src/components/common/AppSidebar.vue`）：

| 业务域 | 入口 |
|---|---|
| 工作台 | 业务交付工作区、本体态势舱、业务应用、系统看版 |
| 数据集成 | 数据接入、资产目录、数据管道、数据血缘、数据质量 |
| 本体中心 | 本体构建（手动 / AI·表单 / 模板 / 文档 / 资产）、本体管理（对象与关系、映射、规则、函数、行动）、图谱探索、本体发布、本体服务 |
| 智能体应用中心 | 智能体管理、技能管理、流程编排（AIP） |
| 场景中心 | 场景管理，下挂边海空情目标研判、无人机反制处置 |
| 运维与安全中心 | 系统看板、运维监控、日志与审计、权限管理、模型配置、系统配置 |

---

## 核心工作流

### 业务交付工作区（六步闭环）

一个交付项目就是一条从需求到可运行应用的链路，六个阶段依次推进，每阶段可回退修改：

1. **需求分析** — 记录业务目标与验收口径
2. **数据源表** — 绑定连接器与物理表
3. **数据处理** — 管道与清洗规则
4. **子图建模** — 从全量本体里裁剪出本项目需要的对象与关系
5. **本体库** — 项目专属本体入库与发布
6. **本体应用** — 在运行时工作区直接查询对象、触发动作

平台对这条链路做**逐步链路校验**（`inspect_chain`），任何一环断了会在对应阶段报错，而不是等到最后应用查不出数据才发现。样例数据落在独立 SQLite 目录，与主库隔离。

### 本体构建

| 方式 | 说明 |
|---|---|
| 手动构建 | 实体、属性、关系 CRUD 与图编辑 |
| AI / 表单建模 | 建模草稿持久化，AI 建议与人工表单共用同一份草稿；带版本号乐观锁，多人编辑不互相覆盖；可复用已发布对象 |
| 模板构建 | 行业标准模板，快速起盘新领域 |
| 文档构建 | 上传 Word/PDF/Excel，LLM 通过 SSE 流式抽取实体与关系 |
| 资产构建 | 基于已接入数据资产的对话式建模 |

配套能力：对象与关系三层级浏览、本体属性 ↔ 物理字段半自动映射（启发式评分 + LLM 兜底）、AntV G6 力导向双层图谱（Schema 层 + 实例层）。

### 发布与质量门禁

草稿 → 审核 → 注水 → 发布，支持回滚。发布前的**水合验证**分四阶段流式推进：数据接入验证（连通性、Schema 同步、样本预览、画像）→ 本体实例化（Token Jaccard + 模糊匹配 + 类型兼容评分，LLM 兜底）→ 关系映射验证（JOIN 键存在性与采样 JOIN）→ 策略输出（主键唯一性、必填字段空值率）。

### 逻辑层

规则管理（表达式与结构化条件双模式）、函数管理（派生属性计算，含 Schema 定义与测试沙箱）、行动管理（参数化业务行动，支持前置条件与手动/自动触发）。规则是受限的声明式规则，不是通用推理引擎。

### 智能体与技能

- **智能体** — ReAct 循环 Agent，注入本体上下文，工具调用与执行追踪
- **技能** — 只读技能为主，明确禁止模型生成 SQL；技能在执行前校验发布指纹，按 `query` / `findings` / `quality` 三类操作运行
- **技能问答** — OpenAI 原生 tool calling，每个 Agent 有独立只读技能白名单，首轮强制调用工具，最多 4 轮，产出可回放的 `AgentTrace`
- **流程编排（AIP）** — 可视化多步骤 Agent 管道，支持 Webhook 触发与调度执行
- **评测与追踪** — 批量评测对比预期输出，全链路记录工具调用明细与 Token 消耗
- **Copilot** — 内嵌对话助手，具备本体、数据、规则的上下文感知

### 场景中心

场景以工厂方式注册（`scene_data.py` 的 `build_scene_router`），当前内置两个可运行场景：边海空情目标研判、无人机反制处置。每个场景有独立演示库，前端做只读聚合展示，研判结论按 OODA 链路写回。

### 客户演示包

一条命令安装一套完整可讲的演示环境，串起"数据接入 → 资产 → 管道 → 本体 → 应用 → 技能 → 问答 → 执行记录"。演示包按项目 owner 隔离，幂等安装，不覆盖已有数据与密钥；只有显式开启 `CHECK_AI=1` 才做真实模型问答。

---

## 系统架构

```text
┌────────────────────────────  前端  Vue 3 + TypeScript + Vite ─────────────────────────────┐
│  工作台 │ 数据集成 │ 本体中心 │ 智能体应用中心 │ 场景中心 │ 运维与安全中心                     │
│  Ant Design Vue · AntV G6 图谱 · VueFlow 编排 · Three.js 三维 · ECharts 看板                │
└──────────────────────────────────────┬────────────────────────────────────────────────────┘
                                  Nginx / Vite 代理
┌──────────────────────────────────────┴────────────────────────────────────────────────────┐
│                       后端  FastAPI + SQLAlchemy 2.0 + Pydantic 2                          │
│  数据平面：连接 · 资产 · 执行 · 探针 · 血缘 · 事件 · 审计 · 对象绑定 · 质量 · 映射            │
│  本体平面：建模 · 草稿 · 映射 · 发布 · 本体服务(OSDK) · 规则 · 函数 · 行动                    │
│  智能平面：Agent · 技能 · 技能问答 · AIP 场景/执行/Webhook · 评测 · 追踪 · Copilot           │
│  平台平面：认证鉴权 · 模型配置 · 系统配置 · 监控 · 看板 · 治理 · 交付项目 · 演示包             │
└───────┬──────────────────────────┬─────────────────────────┬───────────────────────────────┘
        │                          │                         │
   元数据 SQLite/MySQL        外部数据源连接器              LLM 供应商（OpenAI 兼容协议）
   （演示库独立文件）      MySQL·PostgreSQL·Oracle·SQLServer
                        ·SQLite·S3·FTP·Kafka·HTTP API
```

---

## 能力边界

以下结论来自 `docs/technology-capability-matrix.md`，写在这里是为了避免按"完整语义网栈"的预期去验收：

- 平台定位是**业务本体应用平台**：核心是关系数据库中的对象、关系、映射与规则，加上 AI 辅助生成。RDFLib 支持部分 RDF/OWL 文件导入导出，但**没有完整的 OWL 语义一致性推理**；规则是受限的声明式数据约束（必填、比较、集合成员），不是 SWRL，也不提供 OWL 推理完备性
- 元数据默认落在 SQLite；MySQL 为可选后端，Neo4j 与 Redis 当前仅做连接健康检查，未承载图存储与缓存主链路
- 连接器已实现 MySQL、PostgreSQL、Oracle、SQL Server、SQLite、S3、FTP、Kafka、HTTP API；Hive 与 ClickHouse 目前只在数据源类型枚举中出现，尚无连接器实现
- 交付工作区的应用查询有返回行数上限；拖拽式看板、三维孪生、通用推演属后续规划

---

## 技术栈

| 层级 | 技术选型 |
|---|---|
| 前端框架 | Vue 3.5 · TypeScript 6 · Vite 8 · Pinia 3 · Vue Router 4 · Ant Design Vue 4 |
| 可视化 | AntV G6 5（图谱）· VueFlow 1.48（流程编排）· Three.js 0.183（三维）· ECharts 6 |
| 后端框架 | FastAPI 0.115 · Uvicorn 0.34 · SQLAlchemy 2.0 · Pydantic 2.11 · Alembic 1.14 |
| 认证鉴权 | PyJWT · RBAC 中间件 · 审计日志 |
| 数据库 | SQLite（默认）/ MySQL（可选）· Neo4j、Redis（连接检查） |
| 连接器 | MySQL · PostgreSQL · Oracle · SQL Server · SQLite · S3 · FTP · Kafka · HTTP API |
| AI / LLM | OpenAI 兼容协议 · Tool Calling · SSE 流式（sse-starlette）· RDFLib 7.6（RDF/OWL 文件导入导出）· sqlglot 30（SQL 解析） |
| 文档解析 | python-docx · pdfplumber · openpyxl · pandas |
| 交付 | Docker 多阶段构建 · docker-compose · Gitee Go · GitHub Actions |

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+，pnpm 10
- （可选）MySQL 8、Redis、Neo4j

### 源码启动

```bash
# 后端
cd backend
cp .env.example .env          # 配置 DATABASE_URL、LLM_API_BASE 等
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# 前端（另开终端）
cd frontend
pnpm install
pnpm dev
```

访问 `http://localhost:5173`，接口文档 `http://localhost:8001/docs`。

首次启动会依次执行 Alembic 迁移、建表、若干兼容用 `ALTER TABLE`，并写入默认管理员、模型配置与场景注册表；AIP 调度器、数据平面事件总线、管道 Worker 与监控采集器随进程启动。

默认管理员用户名 `admin`，密码取环境变量 `BOOTSTRAP_ADMIN_PASSWORD`，未设置时回落到内置默认值。账号已存在时不会被重置。**部署前请务必显式设置该变量并改掉默认密码。**

### Docker 启动

```bash
cp .env.example .env          # 至少设置 BOOTSTRAP_ADMIN_PASSWORD、SECRET_KEY
docker compose up -d --build  # 前端默认发布在 ${WEB_PORT:-8088}
```

### 运行测试

```bash
cd backend && pytest -q       # 覆盖交付项目、建模草稿、客户演示等用例
```

---

## 配置说明

后端配置文件：`backend/.env`

```env
DATABASE_URL=sqlite:///./ontology.db
# DATABASE_URL=mysql+pymysql://user:pass@host:3306/ontology?charset=utf8mb4
LLM_API_BASE=https://your-llm-endpoint/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model-name
SECRET_KEY=replace-with-strong-random-string
BOOTSTRAP_ADMIN_PASSWORD=change-me
```

生产环境另需 `DEMO_DB_DIR` 指定演示库目录（容器内为 `/app/backend/data`），数据统一持久化在宿主机 `./data/`。凭据建议托管到密钥管理服务，并开启审计日志。

---

## 部署与发布

| 环境 | 方式 | 端口 |
|---|---|---|
| 生产 | `docker-compose.yml`，后端仅容器内 8001 不对外映射 | 前端 `${WEB_PORT:-8088}` |
| UAT | `compose.uat.yml -p ontology-uat`，独立卷与密钥 | 前端 `${UAT_WEB_PORT:-8090}` |

代码仓库采用 Gitee + GitHub 双远程：单位网络推 Gitee 走 Gitee Go，外网推 GitHub 走 Actions，两条流水线都部署同一台 ECS 的 `/opt/ontology`，通过 `/opt/ontology/.deploy.lock` 文件锁互斥，构建失败不会更新运行中的容器。发布后以 nginx 端口的 `/api/v1/scene-registry` 作为健康检查探针。日常部署不重置业务数据；每次发布会幂等安装独立客户演示包（不覆盖已有数据与模型密钥），军事研判与无人机反制的场景种子数据仅在 `SEED_DEMO_DATA=1` 时初始化。

- 双远程与密钥配置：`docs/dual-remote-gitee-github.md`
- GitHub Actions 部署细节：`docs/github-actions-deploy.md`
- 生产操作与自测：`docs/生产环境操作与自测说明.md`
- 一次同时推两边的时序与风险：`docs/dual-pipeline-timeline.html`

---

## 项目结构

```text
backend/
├── app/
│   ├── api/v1/                # REST 接口（40+ 路由模块 + data_plane 子包）
│   │   ├── delivery.py        # 业务交付项目：六步闭环、链路校验、运行时查询与行动
│   │   ├── modeling_drafts.py # AI/表单建模草稿（乐观锁、模板、物化入库）
│   │   ├── customer_demo.py   # 客户演示包状态与安装
│   │   ├── scene_data.py      # 场景路由工厂（军事研判 / 无人机反制）
│   │   ├── builder.py         # 本体构建流水线
│   │   ├── copilot.py         # 对话与 Agent 会话
│   │   └── data_plane/        # 连接、资产、执行、血缘、质量、映射…
│   ├── connectors/            # 可插拔数据源连接器
│   ├── models/                # SQLAlchemy ORM 模型
│   ├── services/
│   │   ├── agent/             # Agent 编排器、工具路由、图引擎
│   │   ├── aip/               # AIP 场景运行器、调度器、事件总线
│   │   ├── builder/           # 注水与水合验证
│   │   ├── data_plane/        # 资产、连接、血缘、质量服务
│   │   ├── business_skills.py # 只读技能注册与执行（禁止模型生成 SQL）
│   │   ├── skill_chat.py      # Tool calling 问答循环与 AgentTrace
│   │   ├── ontology_query.py  # 白名单 + 参数化的实例查询
│   │   └── db_migrations.py   # 启动期 Alembic 升级
│   └── main.py
├── migrations/                # Alembic 版本脚本
├── scripts/customer_demo.py   # 演示包幂等安装
└── tests/                     # 交付项目 / 建模草稿 / 客户演示等用例

frontend/
├── src/
│   ├── api/                   # 类型化 API 客户端
│   ├── components/            # 画布、血缘、本体、演示面板等共享组件
│   ├── composables/           # Vue 组合式工具
│   ├── store/                 # Pinia 状态模块
│   ├── types/                 # TypeScript 类型定义
│   ├── utils/owl/             # OWL 2 序列化工具
│   └── views/                 # 页面组件（workspace/builder/studio/scene/…）
└── package.json

docs/                          # 操作手册、交付与客户演示说明、能力矩阵、部署文档
scripts/deploy/                # 构建、发布、健康检查脚本
.workflow/                     # Gitee Go 流水线定义
.github/workflows/             # GitHub Actions 部署定义
```

---

## 参与贡献

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交变更 (`git commit -m 'Add amazing feature'`)
4. 推送分支 (`git push origin feature/amazing-feature`)
5. 发起 Pull Request

主分支统一使用 `master`。日常推送建议用 `scripts/git-push-both.sh` 一次推两边，确保两条流水线部署的是同一个 commit。

---

## 许可证

[MIT](LICENSE) © 知彼 Ontology
