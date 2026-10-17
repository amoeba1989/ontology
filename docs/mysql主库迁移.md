# 平台主库迁移到 MySQL

## 范围和当前状态

本次迁移仅涉及平台主库：本体定义、属性、关系、规则、用户、配置、草稿、文档元数据等 50 张模型表。MQTT 独立落库、演示 SQLite 数据源、本地/MinIO 文件不随本次迁移改变。

已在隔离 MySQL 8.4 上验证建表与数据迁移。尚未连接或切换用户 ECS 的数据库；当前工作空间 TCP 代理不可用，无法确认正式数据库版本和内容。上传源码 ZIP 不包含原运行环境的 SQLite 数据文件，不能凭源码恢复已有数据。

## 连接配置

推荐 MySQL 8.0/8.4，InnoDB、utf8mb4。创建一个专用空库及专用账号；切勿用已有业务库直接试迁移。账号需要平台表的读写和建表/迁移权限；不需要全实例管理员权限。迁移必须在平台停止写入时进行，导入后切换前不要重启旧实例继续写 SQLite。

复制 `backend/mysql.env.example` 为 `backend/.env`，在服务器本地填写密码。密码作为单独变量传入，可包含 @、#、% 等字符，无需手动 URL 编码。配置不得提交版本库。正式密码由运维安全管理，不写在命令参数、文档、截图或聊天中。

- Python 直接运行：`MYSQL_HOST=127.0.0.1` 仅适用于 MySQL 与应用运行在同一主机网络命名空间。
- Docker 内运行：127.0.0.1 指向应用容器自身。应填容器可访问的 MySQL 服务名或私网地址；MySQL 在 ECS 宿主机时，需配置容器到宿主机的地址/网络及数据库授权，不能照搬 127.0.0.1。
- 跨主机连接：优先私网，按实际网络配置白名单和 TLS；`MYSQL_SSL_CA` 指向可信 CA 文件，Docker 中需要相应挂载。
- 已有 `DATABASE_URL=mysql+pymysql://...` 仍可使用，但推荐单独 MYSQL_* 配置以避免特殊字符转义和凭据外泄。只有 `DATABASE_BACKEND=mysql` 时才使用 MYSQL_*；不会因 MySQL 失败自动回退到 SQLite。

## 迁移步骤（在能访问 MySQL 且持有原数据的 ECS 上执行）

1. 停止所有应用实例及后台写入进程；保留旧部署和上传文件备份。找出实际主 SQLite 文件，例如 Docker 宿主机的 `data/ontology.db`，不要误用无人机 MQTT 或演示数据库。
2. 安装 `backend/requirements.txt`，配置 `backend/.env`。不要先启动应用，否则初始化会往目标库写入管理员和默认配置，使它不再为空。
3. 在 `backend/` 目录执行只读检查：

```bash
python -m scripts.migrate_platform_mysql --check
```

4. 预检源库，路径替换为实际文件；默认不会写入目标库，但会生成 SQLite 一致性备份：

```bash
python -m scripts.migrate_platform_mysql --source /absolute/path/to/ontology.db
```

5. 确认目标是专用空库后导入：

```bash
python -m scripts.migrate_platform_mysql --source /absolute/path/to/ontology.db --apply
```

工具生成权限 0600 的 SQLite 备份，检查完整性和外键；拒绝包含未映射表/列的源库，拒绝有数据的目标库。按外键顺序批量导入，校验每表数量与内容摘要；导入行在一个事务中完成。MySQL DDL 会自动提交，所以失败时可能留下空表；不会删除已有数据，也不会自动切换配置或删除源库。若目标已有数据，需先人工确认备份和迁移方案；不要为了通过检查而清库。

遇到旧版 schema_json 等遗留列或失效外键，工具会拒绝迁移；在备份副本上按现有版本完成兼容升级并复核后重试，不直接修改原件。迁移不包含外部文件、其他业务数据库、用户授权或存储过程。

6. 校验成功后启动应用。Docker 使用 `docker compose --env-file backend/.env up -d --build`，使 Compose 显式传入 MYSQL_*。先核实 MySQL 的网络地址可从容器访问。不要同时启动指向 SQLite 的旧实例。
7. 验收登录、实体/属性/关系、草稿、发布、资产绑定和查询。文件和演示数据源仍需原文件/连接可用。记录验证结果后再恢复业务写入。

## 回退

导入前原 SQLite 和文件备份保持不变。切换后尚未产生新写入时，可停新实例，移除 MYSQL_* 启用设置，恢复原 DATABASE_URL 和 DATABASE_BACKEND=sqlite 再启动。MySQL 一旦有新写入，不应直接退回旧 SQLite，否则会丢失切换后的数据；需要先制定增量数据回迁方案。备份包含敏感业务数据和凭据引用，必须按数据库备份管理。

## 兼容性与验证

MySQL 建表使用 DATETIME(6)、DOUBLE、LONGTEXT，防止日期微秒丢失、浮点精度下降和长文档被 64 KiB TEXT 限制。已有目标表不会自动改变字段类型，因此推荐新建空库，并完成迁移校验。MySQL 默认排序规则可能与 SQLite 不同；若唯一键仅大小写不同，导入可能被拒绝，需要先明确标识符语义并选择合适排序规则。

运行通用安全测试：`python -m pytest tests/test_platform_mysql.py -q`。实际 MySQL 集成测试需要设置仅指向隔离测试服务的 MYSQL_TEST_URL；测试会创建随机 ontology_test_* 数据库并在结束后删除，切勿指向生产实例。

## ECS 一条命令交互切换（推荐）

新版代码部署成功后，在 ECS Workbench 终端执行：

```bash
cd /opt/ontology
python3 scripts/deploy/migrate-main-mysql.py --apply --with-demo
```

脚本默认连接本机 MySQL 管理端口，管理员用户名 `remote_root`，会在 ECS 终端隐藏输入管理密码。密码不会经过聊天或 GitHub。默认新库名为 `ontology_platform_当天日期`，默认应用访问地址为本 ECS 私网 IP `172.22.22.19`；其他环境需显式传入 `--database`、`--admin-user`、`--mysql-host`、`--port`。管理员账号需要创建独立库、独立账号及库级授权的权限。

已有同名目标库时拒绝继续，不会清空。生成独立随机应用密码，权限仅限新库，保存在服务器 `.env`（0600）中。完整过程：获取部署锁 → 检查当前持久化 SQLite → 创建专用库及账号 → 从应用容器测试 MySQL → 停止 ontology 后端 → 一致性备份及逐表迁移校验 → 原子更新配置 → 重建后端并重载 Nginx → 检查 API 和实际 MySQL 连接 → 可选创建新版演示。不会停止 palantir 或 MySQL 服务。

失败时尝试恢复原 `.env` 并启动原后端；保留新库和账号供排查，不擅自删除。原配置备份在 `data/mysql-migration/`，SQLite 备份在 `data/migration-backups/`。如果创建专用库后连通性预检失败，原服务仍运行，可排查 MySQL 的监听地址和授权后重新选择一个新库名执行。

`--with-demo` 添加两个互相独立的新场景：“飞行观测 · 新版演示”和“电商订单 · 新版演示”，共 6 类对象、4 类关系、6 张合成数据表、数据绑定及草稿规则。重复运行 `docker exec ontology-backend python -m scripts.seed_scene_demo` 不会重复生成或覆盖已有记录。旧数据不删除。MySQL 演示连接通过 `platform://` 内部引用复用主库身份，不在数据库中另存密码。

此次切换针对平台主存储；原 MQTT 落库文件和旧演示 SQLite 数据源不在本次迁移范围。新版演示的结构与记录均保存在新的 MySQL 主库。全局场景选择属于展示与查询范围，不替代用户权限或租户隔离。

### 场景浏览与本次边界

顶部「本体场景」选择器按场景登记中的 `domains`、`object_classes` 筛选对象、属性、关系、规则、动作、函数、绑定、资产、血缘、相关智能体及本体版本。对象卡片显示场景标签；跨场景关系不在单场景图谱中展示。新建版本保存场景归属，发布版本不会撤销其他场景的活动版本。

「全部场景」可用于查看和整理历史未归属内容。共享连接、系统配置和建模草稿等尚未建立场景归属的资源仍为全局资源；此功能用于业务内容分类，不代替用户权限控制。MySQL 切换仅覆盖平台主库，外部数据源和原 MQTT/旧演示 SQLite 文件保留。本次新演示使用 MySQL 主库中的两组独立表与场景，不清空历史数据。
