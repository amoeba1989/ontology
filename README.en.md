<div align="center">

# 知彼 Ontology

**Enterprise Ontology Intelligence Platform**

*Ontology-driven · Semantic web of business · Understandable data, trustworthy AI*

**[中文](README.md)** | **[English](README.en.md)**

[![Vue 3](https://img.shields.io/badge/Vue-3.5-4FC08D?logo=vue.js)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![TypeScript](https://img.shields.io/badge/TypeScript-6.x-3178C6?logo=typescript)](https://www.typescriptlang.org/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## Overview

知彼 Ontology consolidates the data scattered across business systems into a single business ontology that is **queryable, reasoning-capable and executable**, and lets intelligent applications be built directly on top of these semantics. The platform is not another BI tool or data catalog; it tackles the problem that the business semantics handed to an AI are otherwise uncontrolled. Once data is ingested, it is first modeled into ontology objects, properties, relationships and rules; the ontology then exposes query and action interfaces to the outside, and agents can only fetch data, reason and act through this governed interface, with every step recorded.

A single thread runs through the whole platform: **ingest data → build the ontology → publish semantics → assemble logic and skills → deliver business applications → run and trace scenarios**. To support this, the platform provides six business domains and a six-step delivery loop, so teams can go from requirements to a runnable business application without writing glue code and without letting the model generate SQL directly.

### Key Highlights

- **Six-step business delivery loop** — Requirement analysis → Source tables → Data processing → Subgraph modeling → Ontology library → Ontology application; each step automatically checks that the chain really holds, and at the end you query objects and run actions directly in the project workspace
- **Five ontology modeling entry points** — manual build, AI/form modeling (drafts are persisted and never overwrite each other across users), template build, document extraction, and conversational asset-based build — covering both cold starts and reverse-modeling from existing data
- **Controlled AI Q&A** — agents can only call registered read-only skills and the model never generates SQL; skill allowlists, a mandatory tool call on the first turn, and end-to-end `AgentTrace` with token accounting
- **Publishing as validation** — the Draft → Review → Hydrate → Publish pipeline is backed by 7 quality gates and four-stage hydration validation, so mappings are run against real data before a release
- **Reusable demos and samples** — built-in customer demo packs and four non-military acceptance samples (chronic disease, literature, BIM, supply chain), installed idempotently with a single command without overwriting existing data or secrets
- **Dual-pipeline delivery** — Gitee Go and GitHub Actions share a file lock so they never step on each other on the same ECS instance, and a failed build leaves the running containers untouched

---

## Platform Overview

The product organizes its navigation around six business domains (see `frontend/src/components/common/AppSidebar.vue`):

| Domain | Entry points |
|---|---|
| Workbench | Business delivery workspace, ontology cockpit, business applications, system dashboard |
| Data Integration | Data ingestion, asset catalog, data pipelines, data lineage, data quality |
| Ontology Center | Ontology construction (manual / AI·form / template / document / asset), ontology management (objects & relationships, mappings, rules, functions, actions), graph exploration, ontology publishing, ontology service |
| Agent Application Center | Agent management, skill management, process orchestration (AIP) |
| Scenario Center | Scenario management, covering border, maritime and air situational target assessment and drone counteraction handling |
| Ops & Security Center | System dashboard, operations monitoring, logs & audit, access control, model configuration, system configuration |

---

## Core Workflow

### Business Delivery Workspace (Six-Step Loop)

A delivery project is a single chain from requirements to a runnable application; the six stages proceed in order, and each can be revisited and revised:

1. **Requirement analysis** — record the business goal and acceptance criteria
2. **Source tables** — bind connectors and physical tables
3. **Data processing** — pipelines and cleansing rules
4. **Subgraph modeling** — cut the objects and relationships this project needs out of the full ontology
5. **Ontology library** — store and publish the project-specific ontology
6. **Ontology application** — query objects and trigger actions directly in the runtime workspace

The platform performs **step-by-step chain validation** (`inspect_chain`) along this link: if any stage breaks, it errors at that stage instead of only surfacing at the end when the application can fetch no data. Sample data lands in a separate SQLite directory, isolated from the main database.

### Ontology Construction

| Approach | Description |
|---|---|
| Manual build | CRUD for entities, properties and relationships with graph editing |
| AI / form modeling | Modeling drafts are persisted, and AI suggestions and manual forms share the same draft; version-number optimistic locking keeps concurrent editors from overwriting each other; published objects can be reused |
| Template build | Industry-standard templates for quickly bootstrapping a new domain |
| Document build | Upload Word/PDF/Excel; the LLM extracts entities and relationships via SSE streaming |
| Asset build | Conversational modeling based on already-ingested data assets |

Supporting capabilities: three-tier browsing of objects and relationships, semi-automatic ontology-property ↔ physical-field mapping (heuristic scoring with an LLM fallback), and an AntV G6 force-directed dual-layer graph (schema layer + instance layer).

### Publishing & Quality Gates

Draft → Review → Hydrate → Publish, with rollback support. The pre-release **hydration validation** proceeds across four streamed stages: data ingestion validation (connectivity, schema sync, sample preview, profiling) → ontology instantiation (token Jaccard + fuzzy matching + type-compatibility scoring, with an LLM fallback) → relationship mapping validation (JOIN-key existence and sampled JOINs) → policy output (primary-key uniqueness, required-field null rate).

### Logic Layer

Rule management (dual-mode expression and structured conditions), function management (derived-property computation with schema definitions and a test sandbox), and action management (parameterized business actions supporting preconditions and manual/automatic triggers). Rules are constrained declarative rules, not a general reasoning engine.

### Agents & Skills

- **Agents** — ReAct-loop agents with injected ontology context, tool calling and execution tracing
- **Skills** — predominantly read-only, explicitly forbidding the model from generating SQL; skills verify a publish fingerprint before running and operate across the three action types `query` / `findings` / `quality`
- **Skill chat** — native OpenAI tool calling; each agent has its own read-only skill allowlist, the first turn is forced to call a tool, up to 4 turns, producing a replayable `AgentTrace`
- **Process orchestration (AIP)** — visual multi-step agent pipelines with webhook triggers and scheduled execution
- **Evaluation & tracing** — batch evaluations compare against expected output, with full-chain logging of tool-call details and token usage
- **Copilot** — an embedded conversational assistant that is context-aware of the ontology, data and rules

### Scenario Center

Scenarios are registered through a factory (`build_scene_router` in `scene_data.py`), with two runnable scenarios currently built in: border, maritime and air situational target assessment, and drone counteraction handling. Each scenario has its own demo store; the frontend provides a read-only aggregate view, and assessment conclusions are written back along the OODA loop.

### Customer Demo Pack

A single command installs a complete, presentable demo environment that strings together data ingestion → assets → pipelines → ontology → application → skills → chat → execution records. Demo packs are isolated by project owner and installed idempotently without overwriting existing data or secrets; real model Q&A runs only when `CHECK_AI=1` is explicitly enabled.

---

## System Architecture

```text
┌───────────────────────────────────────────────── Frontend  Vue 3 + TypeScript + Vite ──────────────────────────────────────────────────┐
│ Workbench │ Data Integration │ Ontology Center │ Agent Application Center │ Scenario Center │ Ops & Security                          │
│ Ant Design Vue · AntV G6 Graph · VueFlow Orchestration · Three.js 3D · ECharts Dashboards                                             │
└───────────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────┘
                                                            Nginx / Vite Proxy
┌───────────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────┐
│ Backend  FastAPI + SQLAlchemy 2.0 + Pydantic 2                                                                                        │
│ Data plane: connections · assets · execution · probes · lineage · events · audit · object binding · quality · mapping                 │
│ Ontology plane: modeling · drafts · mapping · publishing · ontology service (OSDK) · rules · functions · actions                      │
│ AI plane: agents · skills · skill chat · AIP scenarios/execution/webhook · evaluation · tracing · Copilot                             │
│ Platform plane: authentication · model config · system config · monitoring · dashboards · governance · delivery projects · demo packs │
└──┬────────────────────────────────────┬───────────────────────────────────────┬────────────────────────────────────────────────────────┘
   │                                    │                                       │
Metadata SQLite/MySQL                External data source connectors         LLM providers (OpenAI-compatible protocol)
(demo store in a separate file)      MySQL·PostgreSQL·Oracle·SQL Server
                                     ·SQLite·S3·FTP·Kafka·HTTP API
```

---

## Capability Boundaries

The following conclusions come from `docs/technology-capability-matrix.md`, stated here so that no one validates the platform against the expectation of a "full semantic web stack":

- The platform is positioned as a **business ontology application platform**: at its core are objects, relationships, mappings and rules held in a relational database, plus AI-assisted generation. RDFLib handles partial RDF/OWL file import and export, but there is **no full OWL semantic-consistency reasoning**; rules are constrained declarative data constraints (required fields, comparisons, set membership) — not SWRL, and with no OWL reasoning completeness
- Metadata defaults to SQLite; MySQL is an optional backend, and Neo4j and Redis currently only undergo connection health checks; they do not carry the primary graph-store or cache paths
- Connectors are implemented for MySQL, PostgreSQL, Oracle, SQL Server, SQLite, S3, FTP, Kafka and HTTP API; Hive and ClickHouse currently appear only in the data-source type enum and have no connector implementation yet
- Application queries in the delivery workspace have a returned-row cap; drag-and-drop dashboards, 3D twins and general-purpose simulation are future plans

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend framework | Vue 3.5 · TypeScript 6 · Vite 8 · Pinia 3 · Vue Router 4 · Ant Design Vue 4 |
| Visualization | AntV G6 5 (graph) · VueFlow 1.48 (orchestration) · Three.js 0.183 (3D) · ECharts 6 |
| Backend framework | FastAPI 0.115 · Uvicorn 0.34 · SQLAlchemy 2.0 · Pydantic 2.11 · Alembic 1.14 |
| Auth | PyJWT · RBAC middleware · audit logging |
| Database | SQLite (default) / MySQL (optional) · Neo4j, Redis (connection checks) |
| Connectors | MySQL · PostgreSQL · Oracle · SQL Server · SQLite · S3 · FTP · Kafka · HTTP API |
| AI / LLM | OpenAI-compatible protocol · Tool Calling · SSE streaming (sse-starlette) · RDFLib 7.6 (RDF/OWL file import/export) · sqlglot 30 (SQL parsing) |
| Document parsing | python-docx · pdfplumber · openpyxl · pandas |
| Delivery | Docker multi-stage build · docker-compose · Gitee Go · GitHub Actions |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+, pnpm 10
- (Optional) MySQL 8, Redis, Neo4j

### Run from Source

```bash
# Backend
cd backend
cp .env.example .env          # configure DATABASE_URL, LLM_API_BASE, etc.
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Frontend (in another terminal)
cd frontend
pnpm install
pnpm dev
```

Visit `http://localhost:5173`; the API docs are at `http://localhost:8001/docs`.

On first launch it runs the Alembic migrations, creates tables, applies several compatibility `ALTER TABLE` statements, and writes the default administrator, model configuration and scenario registry; the AIP scheduler, the data-plane event bus, the pipeline worker and the monitoring collector start with the process.

The default administrator username is `admin`, and its password comes from the `BOOTSTRAP_ADMIN_PASSWORD` environment variable, falling back to a built-in default when unset. An existing account is never reset. **Before deploying, be sure to set this variable explicitly and change the default password.**

### Run with Docker

```bash
cp .env.example .env          # set at least BOOTSTRAP_ADMIN_PASSWORD and SECRET_KEY
docker compose up -d --build  # the frontend is served on ${WEB_PORT:-8088} by default
```

### Run Tests

```bash
cd backend && pytest -q       # covers delivery projects, modeling drafts, customer demos, etc.
```

---

## Configuration

Backend configuration file: `backend/.env`

```env
DATABASE_URL=sqlite:///./ontology.db
# DATABASE_URL=mysql+pymysql://user:pass@host:3306/ontology?charset=utf8mb4
LLM_API_BASE=https://your-llm-endpoint/v1
LLM_API_KEY=your-api-key
LLM_MODEL=your-model-name
SECRET_KEY=replace-with-strong-random-string
BOOTSTRAP_ADMIN_PASSWORD=change-me
```

For production, additionally set `DEMO_DB_DIR` to the demo store directory (`/app/backend/data` inside the container); data is persisted uniformly under `./data/` on the host. Credentials should be kept in a key management service, and audit logging enabled.

---

## Deployment & Release

| Environment | Method | Port |
|---|---|---|
| Production | `docker-compose.yml`; the backend listens on 8001 inside the container only and is not exposed | Frontend `${WEB_PORT:-8088}` |
| UAT | `compose.uat.yml -p ontology-uat`, with separate volumes and secrets | Frontend `${UAT_WEB_PORT:-8090}` |

The repository uses a Gitee + GitHub dual-remote setup: pushing to Gitee from the internal network runs Gitee Go, pushing to GitHub from the external network runs Actions, and both pipelines deploy to the same `/opt/ontology` on one ECS instance, mutually excluding through the `/opt/ontology/.deploy.lock` file lock so a failed build never updates the running containers. After a release, the health probe is `/api/v1/scene-registry` served on the nginx port. Routine deployments never reset business data; each release idempotently installs the isolated customer demo pack (leaving existing data and model keys untouched), while the military-assessment and counter-drone scene seed data initialize only when `SEED_DEMO_DATA=1`.

- Dual-remote and secret setup: `docs/dual-remote-gitee-github.md`
- GitHub Actions deployment details: `docs/github-actions-deploy.md`
- Production operations and self-tests: `docs/生产环境操作与自测说明.md`
- Timing and risks of pushing to both at once: `docs/dual-pipeline-timeline.html`

---

## Project Structure

```text
backend/
├── app/
│   ├── api/v1/                # REST endpoints (40+ route modules + the data_plane subpackage)
│   │   ├── delivery.py        # business delivery projects: six-step loop, chain validation, runtime queries and actions
│   │   ├── modeling_drafts.py # AI/form modeling drafts (optimistic locking, templates, materialized import)
│   │   ├── customer_demo.py   # customer demo pack status and installation
│   │   ├── scene_data.py      # scenario router factory (military assessment / drone counter-action)
│   │   ├── builder.py         # ontology build pipeline
│   │   ├── copilot.py         # conversations and agent sessions
│   │   └── data_plane/        # connections, assets, execution, lineage, quality, mapping…
│   ├── connectors/            # pluggable data-source connectors
│   ├── models/                # SQLAlchemy ORM models
│   ├── services/
│   │   ├── agent/             # agent orchestrator, tool router, graph engine
│   │   ├── aip/               # AIP scenario runner, scheduler, event bus
│   │   ├── builder/           # hydration and hydration validation
│   │   ├── data_plane/        # asset, connection, lineage and quality services
│   │   ├── business_skills.py # read-only skill registration and execution (the model is forbidden from generating SQL)
│   │   ├── skill_chat.py      # tool-calling chat loop and AgentTrace
│   │   ├── ontology_query.py  # allowlist + parameterized instance queries
│   │   └── db_migrations.py   # startup-time Alembic upgrade
│   └── main.py
├── migrations/                # Alembic version scripts
├── scripts/customer_demo.py   # idempotent demo-pack installation
└── tests/                     # test cases for delivery projects / modeling drafts / customer demos, etc.

frontend/
├── src/
│   ├── api/                   # typed API client
│   ├── components/            # shared components for the canvas, lineage, ontology, demo panels, etc.
│   ├── composables/           # Vue composables
│   ├── store/                 # Pinia state modules
│   ├── types/                 # TypeScript type definitions
│   ├── utils/owl/             # OWL 2 serialization utilities
│   └── views/                 # page components (workspace/builder/studio/scene/…)
└── package.json

docs/                          # operations guides, delivery and customer-demo notes, the capability matrix and deployment docs
scripts/deploy/                # build, release and health-check scripts
.workflow/                     # Gitee Go pipeline definitions
.github/workflows/             # GitHub Actions deployment definitions
```

---

## Contributing

1. Fork this repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

The main branch is `master` throughout. For routine pushes, use `scripts/git-push-both.sh` to push to both remotes at once, ensuring both pipelines deploy the same commit.

---

## License

[MIT](LICENSE) © 知彼 Ontology
