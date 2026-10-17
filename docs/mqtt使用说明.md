# minsim 仿真引擎 · 使用说明

> **本文是 minsim 唯一的对外使用文档**，面向：要跑引擎的人、要写想定文件的人、要基于 MQTT 对接的外部系统（前端页面、想定编排器、态势显示器、测试脚本）。
>
> 内容涵盖：命令行与配置、MQTT 接口（主题与报文）、想定文件完整格式、控制指令、端到端时序、客户端示例、限制与排障。**只讲怎么用，不讲内部实现。**
>
> 全部约定以当前代码实现为准。

---

## 目录

1. [引擎是什么](#1-引擎是什么)
2. [快速上手](#2-快速上手)
3. [命令行与配置](#3-命令行与配置)
4. [MQTT 连接与主题](#4-mqtt-连接与主题)
5. [下行：态势与事件](#5-下行态势与事件)
6. [上行：控制指令与想定上传](#6-上行控制指令与想定上传)
7. [想定文件完整格式](#7-想定文件完整格式)
8. [端到端交互时序](#8-端到端交互时序)
9. [客户端示例](#9-客户端示例)
10. [限制与注意事项](#10-限制与注意事项)
11. [排障](#11-排障)
12. [关键常量速查](#12-关键常量速查)

---

## 1. 引擎是什么

minsim 是一个离散时间步进的无人机对抗仿真引擎。它负责**按想定推演世界**，并通过 MQTT 与外界交换数据。

```
┌──────────────────────┐        ┌───────────┐        ┌───────────────────────┐
│   前端页面 (浏览器)   │◀──────▶│   MQTT    │◀──────▶│      minsim 引擎       │
│  地图 / 编排 / 控制    │  ws://  │  broker   │  tcp:// │  C + Flecs ECS 内核    │
└──────────────────────┘        └───────────┘        └───────────────────────┘
      MQTT over WebSocket                            MQTT over TCP
```

核心约定：

- 引擎是一个**普通 MQTT 客户端**，与外部系统**不直接互联**，全部经由 **broker** 解耦。
- **MQTT 是引擎与外界唯一的通道**（无 HTTP / WebSocket 业务接口 / 控制台）。
- 引擎对外**只收发 WGS-84 经纬高**，内部坐标换算由引擎在边界完成——**使用方只需按经纬度发送与接收**。
- 引擎**每推进一步**发布一条态势（默认步长 0.02 s ⇒ 50 Hz）。
- 引擎有两类运行模式：
  - **单次运行**：命令行指定想定，跑完即退出；
  - **常驻服务（`serve`）**：等待 MQTT 上传想定，逐份推演（**外部对接必须用这个模式**）。

你能用它做的事：想定编排并上传、订阅态势做可视化、暂停/恢复/停止/调倍速、展示实体状态与告警。

---

## 2. 快速上手

### 2.1 运行引擎

引擎的可执行文件是 `sim`（构建方式见仓库根目录 `README.md`）。两条最常用命令：

```bash
# 单次运行：加载想定 -> 推演 -> 退出（默认命令，可直接跟想定文件）
sim run scenarios/demo_scenario.json

# 常驻服务：连 broker，等待外部上传想定（对接前端必须用这个）
sim serve \
  --broker tcp://127.0.0.1:1883 \
  --topic-prefix minsim \
  --client-id minsim-core \
  --qos 1
```

启动成功日志会打印：

```
MQTT 已连接 tcp://127.0.0.1:1883 | 下行=minsim/telemetry 上行=minsim/command,minsim/scenario
```

> **前端跑在浏览器里**，必须用 **WebSocket**（`ws://`）连 broker，且 broker 需开启 WebSocket 监听端口（如 EMQX 8083）。引擎侧用 `tcp://` 或 `ws://` 均可。

### 2.2 一次典型对接流程

1. 启动 broker（如 mosquitto / EMQX）。
2. 启动引擎常驻服务：`sim serve --broker ...`。
3. 外部系统订阅 `<prefix>/telemetry`（态势）。
4. 外部系统向 `<prefix>/scenario` 发布想定 JSON → 引擎解析、实例化并**自动开跑**。
5. 推演过程中可向 `<prefix>/command` 发控制指令；结束时发 `{"action":"stop"}`。
6. 上传下一份想定即开始新场景（场景号 +1）。
7. **多客户端并发**：把上一步的主题插入一个唯一的 `client` 段（如 `minsim/uav01/scenario`）即可，每个 `client` 独立一路推演、互不干扰；详见 §4.4。

---

## 3. 命令行与配置

`sim` 采用 git 风格子命令。

### 3.1 子命令

| 命令 | 说明 |
| --- | --- |
| `sim run [想定文件]` | 单次运行：加载想定 → 推演 → 退出（默认命令） |
| `sim serve` | 常驻服务：等待 MQTT 上传想定 → 推演 → 等待下一份 |
| `sim scenario check <文件>` | 校验想定文件（解析 + 实例化检查） |
| `sim scenario example` | 打印一份最小可用想定 JSON |
| `sim config <子命令>` | 管理用户配置 `~/.sim/config`（`get` / `set` / `unset` / `show` / `init`） |
| `sim test` | 运行内置自检 |
| `sim version` | 显示版本 |
| `sim help` | 显示帮助 |

> 未识别的首个参数会被当作想定文件，等价于 `sim run <想定文件>`。
> 也支持 `sim --serve`（等价 `sim serve`）。

### 3.2 选项（`run` / `serve` 通用）

| 选项 | 含义 |
| --- | --- |
| `-c, --config <path>` | 附加配置文件 |
| `--scenario <path>` | 想定 JSON 文件（也可作为位置参数） |
| `--steps <n>` | 每场景最大推进步数，`0` = 不限（**默认 0**，需外部 `stop` 结束） |
| `--step-seconds <f>` | 固定步长，单位秒（默认 `0.02`） |
| `--speed <f>` | 仿真倍速（默认 `1.0`） |
| `--realtime` | 按真实时间节流推进（**默认开启**） |
| `--no-realtime` | 全速推进 |
| `--scenario-id <n>` | 场景标识基值，`0` = 首个场景为 1 并递增（默认 `0`） |
| `--origin-lat/-lon/-alt` | 全局参考原点（想定未声明 `world.origin` 时生效） |
| `--broker <uri>` | MQTT broker，如 `tcp://host:1883`、`ws://10.5.23.205:8083`；留空 = 降级（不建链、态势丢弃） |
| `--topic-prefix <p>` | 主题前缀，默认 `minsim` |
| `--client-id <id>` | MQTT 客户端标识，默认 `minsim-core`（**多进程并存必须各不相同**） |
| `--username <name>` | MQTT 用户名（broker 要求认证时必填） |
| `--password <pass>` | MQTT 密码（配合 `--username`） |
| `--qos <0\|1\|2>` | 发布/订阅 QoS，默认 `1` |
| `--max-clients <n>` | 常驻模式并发**具名会话**上限，默认 `32`；运行期可用 `<prefix>/admin` 动态扩容（详见 §4.4） |
| `--log-level <level>` | `trace` / `debug` / `info` / `warn` / `error`（默认 `info`） |
| `--log-file <path>` | 额外把日志追加落盘 |
| `-h, --help` | 显示帮助 |
| `--version` | 显示版本 |

### 3.3 配置文件

配置为纯文本，每行一个 `键 = 值`。可用 `sim config init` 生成带注释的模板到 `~/.sim/config`。

- `#` 或 `;` 开头为整行注释；取值后空一格再写 `#` 为行内注释。
- 取值含空格时用双引号包裹，如 `log_file = "D:/logs/minsim.log"`。
- 键名可用下划线或连字符，大小写不敏感（`scenario_id` 与 `scenario-id` 等价）。
- **未知键会报错退出**，便于发现拼写错误。

**优先级（高 → 低）：命令行 > `-c` 指定文件 > `~/.sim/config` > 内置默认。**

常用键：

```
serve / scenario / steps / step_seconds / speed / realtime / scenario_id
origin_lat / origin_lon / origin_alt
broker / topic_prefix / client_id / username / password / qos / max_clients
log_level / log_file
```

示例（`sim serve -c <文件>` 或写入 `~/.sim/config`）：

```
serve        = true
scenario     = scenarios/demo_scenario.json   # 常驻模式下的首次推演
steps        = 0
step_seconds = 0.02
speed        = 1.0
realtime     = true
origin_lat   = 39.907
origin_lon   = 116.391
origin_alt   = 50.0
broker       = tcp://127.0.0.1:1883
topic_prefix = minsim
client_id    = minsim-core
username     = JavaServer        # broker 要求认证时必填，留空=匿名连接
password     = 123456
qos          = 1
```

### 3.4 想定的三种加载方式

| 方式 | 用法 | 适用 |
| --- | --- | --- |
| 命令行 | `sim run scenarios/demo_scenario.json`（或 `sim run --scenario <文件>`） | 单次运行 / 调试 |
| 配置文件 | `scenario = scenarios/demo_scenario.json` | 常驻模式下的首次推演 |
| **MQTT 上传** | 向 `<topic_prefix>/scenario` 发布想定 JSON | 常驻服务运行中动态换场景 |

### 3.5 运行时降级行为

- **未配置 `broker`**（或为空）：服务照常启动，但不建立连接，所有下行报文直接丢弃（日志告警）；**推演全速照跑**。
- 未开启 cJSON 支持时（非默认，参见构建文档）：想定只做文件校验，**不实例化任何实体**，日志会打印告警。

---

## 4. MQTT 连接与主题

### 4.1 连接参数

| 参数 | 命令行 | 配置文件键 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| broker | `--broker <uri>` | `broker` | 空 | 如 `tcp://127.0.0.1:1883`、`ws://10.5.23.205:8083`；**留空 = 降级模式** |
| 主题前缀 | `--topic-prefix <s>` | `topic_prefix` | `minsim` | 最终主题 = `<前缀>/telemetry` 等 |
| 客户端 ID | `--client-id <s>` | `client_id` | `minsim-core` | **多进程并存时必须各不相同**，否则会互相踢下线 |
| QoS | `--qos <0\|1\|2>` | `qos` | `1` | 同时用于发布与订阅 |
| 并发会话上限 | `--max-clients <n>` | `max_clients` | `32` | **具名会话**数上限（默认会话不占额度）；运行期可用 `<prefix>/admin` 扩容 |
| 用户名/密码 | `--username` / `--password` | `username` / `password` | 空 | broker 要求认证时必填；留空 = 匿名连接 |

### 4.2 连接行为（固定，不可配）

| 项 | 取值 |
| --- | --- |
| MQTT 协议版本 | 3.1.1 |
| 会话 | `cleansession = 1`（不保留会话状态） |
| KeepAlive | 30 秒 |
| 连接超时 | 5 秒 |
| 断线重连 | 每 **2 秒**自动重试，无限次 |
| 传输 | `tcp://` 与 `ws://` 均支持 |
| TLS/SSL | **不支持** |
| 遗嘱消息 (LWT) | **未设置** |
| retained | 发布时固定 `retained = 0` |

> **重要**：引擎发布**不使用 retained**，因此外部**连上后收不到历史态势**，必须等下一帧（约 20 ms）。刷新页面 / 断线重连后只能从当前时刻重新累积。

### 4.3 主题一览

引擎同时承载**默认会话**与多路**具名会话**：主题在 `<prefix>` 之后是否插入一个 `client` 段，即区分不同会话。

| 主题 | 方向 | 引擎角色 | 载荷 | 用途 |
| --- | --- | --- | --- | --- |
| `<prefix>/telemetry` | **下行** | 发布 | 态势 JSON | 默认会话态势，每推进一步一条 |
| `<prefix>/event` | **下行** | 发布 | 事件 JSON | 默认会话事件（见 §5.2） |
| `<prefix>/command` | **上行** | 订阅 | 指令 JSON | 默认会话控制指令 |
| `<prefix>/scenario` | **上行** | 订阅 | 想定 JSON | 默认会话想定上传 |
| `<prefix>/<client>/telemetry` | **下行** | 发布 | 态势 JSON | 具名会话 `<client>` 的态势 |
| `<prefix>/<client>/event` | **下行** | 发布 | 事件 JSON | 具名会话 `<client>` 的事件（含会话超限告警） |
| `<prefix>/<client>/command` | **上行** | 订阅 | 指令 JSON | 具名会话 `<client>` 的控制指令 |
| `<prefix>/<client>/scenario` | **上行** | 订阅 | 想定 JSON | 具名会话 `<client>` 的想定上传 |
| `<prefix>/admin` | **上行** | 订阅 | 管理 JSON | 管理面：运行期动态扩容等（见 §4.4） |

> 主题拼接规则：前缀结尾多余的 `/` 会被去掉；前缀为空时退化为 `minsim/xxx`（默认前缀 `minsim`）。
> 引擎内部订阅 5 个主题：`<prefix>/command`、`<prefix>/scenario`、`<prefix>/+/command`、`<prefix>/+/scenario`、`<prefix>/admin`。

### 4.4 多客户端并发

引擎单进程即可同时承载**多路互不干扰**的仿真，每个客户端对应一条独立的推演线程与一份独立的想定实例。

**核心规则**

| 规则 | 说明 |
| --- | --- |
| 会话标识 | `client` 段由**前端自行生成**的唯一串（如 `uav01`、`client-a1b2`）；引擎按主题中的该段识别会话，不做校验 |
| 会话隔离 | 每个 `client` 拥有独立的坐标系原点、想定实例、输入/输出队列与推演线程，互不影响 |
| 单会话单想定 | 每个 `client` 同一时刻只跑**一份**想定；同 `client` 重新上传想定 → **先停止旧推演，再启动新想定** |
| 并发上限 | 具名会话数默认上限 **32**（`--max-clients` / `max_clients`）；**默认会话不占此额度** |
| 超限处理 | 会话数已达上限时，**拒绝新会话**，并向触发者 `<prefix>/<client>/event` 发事件码 `1001`（见 §5.2） |
| 动态扩容 | 向 `<prefix>/admin` 发布 `{"action":"capacity","value":N}` 把上限提高到 `N`（**只增不减**），立即对新会话生效；已在跑的会话不受影响 |

**示例：两个客户端并发**

```text
客户端 A：订阅 minsim/uav01/telemetry   发布 minsim/uav01/scenario
客户端 B：订阅 minsim/uav02/telemetry   发布 minsim/uav02/scenario
```

```bash
mosquitto_pub -h 10.5.23.205 -p 1883 -t 'minsim/uav01/scenario' -f scenario_a.json
mosquitto_pub -h 10.5.23.205 -p 1883 -t 'minsim/uav02/scenario' -f scenario_b.json
# 运行期扩容到 64 路
mosquitto_pub -h 10.5.23.205 -p 1883 -t 'minsim/admin' -m '{"action":"capacity","value":64}'
```

**注意事项**

- `client` 段**不要**与固定叶子名冲突（`command` / `scenario` / `telemetry` / `event` / `admin`）。
- `client` 段为**单层**：`minsim/a/b/command` 不匹配任何订阅，会被忽略。
- 同一个 `client` 想定**重发即重启**：无需先手动 `stop`，但会打断当前进度（场景号重新分配）。
- 需要"会话级"指令（暂停/停止/倍速）时，请发到该会话自己的 `<prefix>/<client>/command`，不要发到默认主题。

---

## 5. 下行：态势与事件

### 5.1 态势 `<prefix>/telemetry`

引擎**每个推演步**发布 1 条，QoS = 配置值，无 retained。

**报文示例**

```json
{
  "type": "telemetry",
  "tick": 123,
  "client": "",
  "sim_time_s": 2.4600,
  "scenario_id": 1,
  "scenario_name": "demo_area_defense",
  "entity_count": 6,
  "reported_count": 6,
  "step_ms": 0.0430,
  "entities": [
    {
      "id": 512,
      "name": "uav_quad_01",
      "blocks": 63,
      "transform": {
        "latitude_deg": 39.90429810,
        "longitude_deg": 116.39450838,
        "altitude_m": 50.000,
        "yaw_deg": 0.000,
        "pitch_deg": 0.000,
        "roll_deg": 0.000
      },
      "motion": { "speed_mps": 12.000, "mode": 6 },
      "flight": { "airspeed_mps": 12.000 },
      "faction": { "side": 2 },
      "rf_link": {
        "gnss_locked": true,
        "rc_linked": true,
        "telemetry_linked": true,
        "gnss_sir_db": 20.00,
        "rc_sir_db": 18.00
      },
      "health": { "hp": 100.0, "max_hp": 100.0, "destroyed": false }
    },
    {
      "id": 513,
      "name": "jammer_01",
      "blocks": 73,
      "transform": {
        "latitude_deg": 39.90700000,
        "longitude_deg": 116.39100000,
        "altitude_m": 70.000,
        "yaw_deg": 0.000,
        "pitch_deg": 0.000,
        "roll_deg": 0.000
      },
      "faction": { "side": 1 },
      "jammer": {
        "enabled": true,
        "emitting": true,
        "style": 1,
        "eirp_dbm": 59.0,
        "freq_hz": 1575420000,
        "bandwidth_hz": 20000000,
        "boresight_yaw_deg": 0.00,
        "boresight_pitch_deg": 15.00,
        "half_angle_deg": 30.00,
        "sidelobe_gain_dbi": 0.00
      }
    }
  ]
}
```

> **块化载荷（重要）**：每个实体 = 基础标识（`id` / `name`）+ 块掩码 `blocks` + 若干**态势块**。
> 一个块对应内核的一个组件，但**块位序是消息层自有契约**（见 §5.1 态势块一览），不随内核组件调整。
> **`blocks` 未置位的块在报文中整块省略**：例如上面的干扰机没有 `motion` / `rf_link` / `health`。
> 前端**必须先读 `blocks`，再按需读取对应块字段**，不要假设所有字段恒在。
> 设备类型不同 → 块组合不同；新增反制设备/无人机类型只是新增一种块组合，旧的实体不受影响。

**顶层字段**

| 字段 | 类型 | 精度 | 说明 |
| --- | --- | --- | --- |
| `type` | 字符串 | — | 固定 `"telemetry"` |
| `tick` | 整数 | — | 推演步号，从 1 起递增 |
| `client` | 字符串 | — | 会话标记，空串为默认会话（见 §4） |
| `sim_time_s` | 数 | 4 位小数 | 仿真时刻（秒）= `tick × step_seconds` |
| `scenario_id` | 整数 | — | 场景号，由引擎分配（见 §6.2） |
| `scenario_name` | 字符串 | — | 想定名（最长 31 字符随报文回传） |
| `entity_count` | 整数 | — | 世界内实体**总数** |
| `reported_count` | 整数 | — | **本条报文实际携带**的实体数（≤ 256） |
| `step_ms` | 数 | 4 位小数 | 本步内核耗时（毫秒），可用于监控 |
| `entities` | 数组 | — | 实体快照数组 |

**实体基础字段**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | 整数 | 实体句柄，**同一次运行内唯一**（跨运行可能复用，勿持久化为主键） |
| `name` | 字符串 | 实体名 |
| `blocks` | 整数 | 有效块位掩码（下表位或）；未置位的块不出现在报文里 |

**态势块一览**（`blocks & 位` 为真即表示该块存在）

| 块 | 位 | 来源组件 | 说明 |
| --- | --- | --- | --- |
| `transform` | 1 | CompTransform | 位姿（经纬高 + 三轴姿态） |
| `motion` | 2 | CompMotion | 地速 + 运动模式 |
| `flight` | 4 | CompFlightState | 空速 |
| `faction` | 8 | CompFaction | 阵营 |
| `rf_link` | 16 | CompUavRfLink | 射频链路状态 |
| `health` | 32 | CompUavHealth | 生命值 / 摧毁 |
| `jammer` | 64 | CompJammerEmitter | 干扰源配置 + 本帧发射状态 |

**各块字段**

`transform`（位置为 WGS-84 经纬高，可直接上图）

| 字段 | 类型 | 精度 | 说明 |
| --- | --- | --- | --- |
| `latitude_deg` | 数 | 8 位小数 | WGS-84 纬度（度） |
| `longitude_deg` | 数 | 8 位小数 | WGS-84 经度（度） |
| `altitude_m` | 数 | 3 位小数 | 海拔高度（米） |
| `yaw_deg` | 数 | 3 位小数 | 航向，**0 = 正北，顺时针为正** |
| `pitch_deg` | 数 | 3 位小数 | 俯仰角 |
| `roll_deg` | 数 | 3 位小数 | 滚转角 |

`motion`

| 字段 | 类型 | 精度 | 说明 |
| --- | --- | --- | --- |
| `speed_mps` | 数 | 3 位小数 | 地速 |
| `mode` | 整数 | — | 运动模式，见下表 |

`flight`

| 字段 | 类型 | 精度 | 说明 |
| --- | --- | --- | --- |
| `airspeed_mps` | 数 | 3 位小数 | 空速（无风时等于地速） |

`faction`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `side` | 整数 | `0` 中立 / `1` 红方 / `2` 蓝方 |

`rf_link`

| 字段 | 类型 | 精度 | 说明 |
| --- | --- | --- | --- |
| `gnss_locked` | 布尔 | — | 卫导锁定 |
| `rc_linked` | 布尔 | — | 遥控链路在线 |
| `telemetry_linked` | 布尔 | — | 遥测链路在线 |
| `gnss_sir_db` | 数 | 2 位小数 | 卫导干信比 (dB) |
| `rc_sir_db` | 数 | 2 位小数 | 遥控干信比 (dB) |

`health`

| 字段 | 类型 | 精度 | 说明 |
| --- | --- | --- | --- |
| `hp` | 数 | 1 位小数 | 当前生命值 |
| `max_hp` | 数 | 1 位小数 | 最大生命值（供前端直接换算百分比） |
| `destroyed` | 布尔 | — | 是否已摧毁 |

`jammer`（干扰源 = 反制设备）

| 字段 | 类型 | 精度 | 说明 |
| --- | --- | --- | --- |
| `enabled` | 布尔 | — | 设备总开关 |
| `emitting` | 布尔 | — | 本帧**实际**是否在发射（已含通/断周期判定，与 `enabled` 不等价） |
| `style` | 整数 | — | 干扰样式，见下表 |
| `eirp_dbm` | 数 | 1 位小数 | 有效辐射功率 = 发射功率(dBm) + 主瓣增益(dBi) |
| `freq_hz` | 数 | 0 位小数 | 中心频率（Hz） |
| `bandwidth_hz` | 数 | 0 位小数 | 干扰带宽（Hz） |
| `boresight_yaw_deg` | 数 | 2 位小数 | 波束指向方位角（0 = 正北、顺时针） |
| `boresight_pitch_deg` | 数 | 2 位小数 | 波束指向俯仰角（0 = 水平、向上为正） |
| `half_angle_deg` | 数 | 2 位小数 | 主瓣半锥角（度）；≤ 0 视为全向 |
| `sidelobe_gain_dbi` | 数 | 2 位小数 | 波束外方向的旁瓣增益（dBi） |

> 干扰源块**不携带等效作用距离**：作用距离由 EIRP、频率与目标接收端门限反推，随目标而异，
> 属目标侧参数，前端如需要可按 `eirp_dbm` / `freq_hz` 与目标链路自行估算。

`motion.mode` 映射（建议据此切换图标 / 颜色）：

| 值 | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 含义 | IDLE | CRUISE | LOST_LINK | FALLING | RETURN_HOME | DESTROYED | ROUTE |
| 中文 | 静止 | 巡航 | 失控 | 下坠 | 返航 | 已摧毁 | 沿航路 |

`jammer.style` 映射：

| 值 | 0 | 1 | 2 |
| --- | --- | --- | --- |
| 含义 | BARRAGE | SPOT | SWEPT |
| 中文 | 阻塞 | 瞄准（点频） | 扫频 |

> **坐标系**：态势坐标为 **WGS-84 经纬高**，可直接对接地图库（Leaflet / Cesium / Mapbox 等）。引擎负责与内部坐标的换算，**使用方不需要知道参考原点，也不要做任何坐标换算**。

**容量限制与截断**

| 限制 | 值 | 越界行为 |
| --- | --- | --- |
| 单条报文最大字节 | 262144（256 KB） | 超长时**整条**替换为 `{"type":"telemetry","truncated":true}` |
| 单帧最多实体数 | 256 | 超出部分本帧不携带（`entity_count` 与 `reported_count` 不等即表示被截断） |

> 判定：若 `reported_count < entity_count`（本帧被截断），或收到 `truncated: true`（整条被替换，无 `entities`），应给出提示而非崩溃。

### 5.2 事件 `<prefix>/event`

格式：

```json
{ "type": "event", "tick": 42, "code": 3, "text": "gnss lost" }
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `type` | 字符串 | 固定 `"event"` |
| `tick` | 整数 | 事件产生步号 |
| `code` | 整数 | 事件码（由产生方定义，见下表） |
| `text` | 字符串 | 事件描述（最长 127 字符） |

**已定义事件码**

| `code` | 产生方 | 主题 | 含义 |
| --- | --- | --- | --- |
| `1001` | 网络层 | `<prefix>/<client>/event` | **会话数超限**：新会话被拒绝；`text` 形如 `会话数已达上限 32，拒绝新会话 'uav33'`。可用 `<prefix>/admin` 扩容后重试（见 §4.4） |

> **除 1001 外的业务事件：内核尚未产生。** 可以订阅该主题并写好处理逻辑，但在引擎补齐事件生产前不会收到业务事件报文。
> 需要"告警"展示时，**请暂时从态势字段自行推断**，例如：
> - `gnss_locked == false` → 导航失锁；`rc_linked == false` → 遥控失控；
> - `motion_mode == 3`(FALLING) / `2`(LOST_LINK) / `5`(DESTROYED) → 异常状态；
> - `hp` 下降 / `destroyed == true` → 毁伤。

---

## 6. 上行：控制指令与想定上传

### 6.1 控制指令 `<prefix>/command`

支持的指令：

| `action` | `value` | 效果 |
| --- | --- | --- |
| `start` | 忽略 | 启动推演（**上传想定后已自动开跑，正常无需手发**） |
| `pause` | 忽略 | 暂停推进（暂停期间仍响应 `resume` / `stop`） |
| `resume` | 忽略 | 恢复推进 |
| `stop` | 忽略 | **结束当前场景**；常驻模式下回到"等待下一份想定" |
| `speed` | **必须 > 0** | 调整仿真倍速；`value <= 0` 被忽略 |

其它 `action`：记录 warning 并忽略。

报文示例：

```json
{ "action": "pause" }
```

```json
{ "action": "speed", "value": 2.0 }
```

**解析规则**：上行指令用**标准 JSON 解析器**（cJSON）读取字段：

1. `action`：取对象里的字符串值。
2. `value`：取数字值；**缺失或非数字按 0 处理**。
3. 报文不是合法 JSON、或找不到 `action` → 忽略该报文。

因此必须遵守：

- 载荷必须是**合法 JSON 对象**，形如 `{"action":"xxx"}`。
- **键名大小写敏感**：`action` / `value` 须全小写；`{"Action":"pause"}` 不生效。
- 键序、空白、字符串转义均不受限制；可自由附带自定义字段（忽略），字段值内容不会干扰解析。

> **当前控制粒度是"整个场景"**，暂不支持对单个实体下指令（如"让 3 号机返航""打开 2 号干扰机"）。
> **控制指令作用于收到它的那个会话**：发到 `<prefix>/command` 影响默认会话，发到 `<prefix>/<client>/command` 只影响该具名会话（见 §4.4）。

### 6.2 想定上传 `<prefix>/scenario`

向常驻服务推送一份**完整想定 JSON**，引擎解析 → 实例化实体 → **自动开始推演**。
**具名会话**上传到 `<prefix>/<client>/scenario`（见 §4.4），各自独立；下表的"当前场景"均指**该会话自己的**推演。

| 行为 | 说明 |
| --- | --- |
| 载荷 | **完整想定 JSON 原样**，不经指令解析、**不受 128 KB 报文限制**（走原始 payload，仅受 broker 包上限约束） |
| 缓存 | **每会话只保留最近一条**；上一条被取走前连发多份，只有最后一份生效 |
| 取用时机 | 主管线程**空闲时**取走；该会话**正在运行时，新想定会先停止旧推演再启动新的**（同 `client` 重发 = 先停后起） |
| 解析失败 | 记录 error 并丢弃，继续等待下一份（服务不退出） |
| 生效前提 | **必须 `serve` 常驻模式**；单次运行模式不监听该主题 |
| 超限拒绝 | 具名会话数已达上限时，新会话被拒绝并回事件码 `1001`（见 §4.4） |

> **无回执**：引擎不会回答"想定已受理/解析成功/实体数"。唯一反馈是**随后是否出现新 `scenario_id` 的态势**。若长时间无新态势，请检查：是否 `serve`、当前是否仍有场景在跑（需先 `stop`）、JSON 是否合法。

**场景生命周期与切换**

```
引擎启动 (serve)
   │  若配置了 scenario 文件 → 先跑这份"首次推演"（默认会话）
   ▼
等待 <prefix>[/<client>]/scenario ──收到想定──▶ 解析 → 实例化 → 自动 start → 推进
   ▲                                                          │
   └────── 本场景结束（达到 steps 上限 / 收到 stop / 同会话收到新想定）──────┘
```

- **`--steps 0` = 不限步数**，场景会一直推进，必须外部发 `stop`（或重传想定）才能结束并接收下一份想定。
- **切换场景**：手动方式先 `stop` 结束当前，再上传新想定；**或直接重传想定**——同 `client` 重发会先停旧再起新（见 §4.4）。
- **场景号 `scenario_id`**：引擎自动分配并递增——默认（`--scenario-id 0`）首个场景为 `1`，此后每份 +1；若显式设 `--scenario-id N`，首个场景为 `N` 再递增。用它区分不同场景的态势。

**多场景并存**

- **单进程多会话**（推荐）：一份想定发到 `<prefix>/<client>/scenario`，最多 32 路（可扩容），见 §4.4。
- **多进程**：需要完全独立的进程边界时，用不同前缀各自起一个进程：

```bash
sim serve --scenario-id 101 --client-id minsim-s101 --topic-prefix minsim/s101 --broker tcp://127.0.0.1:1883 &
sim serve --scenario-id 202 --client-id minsim-s202 --topic-prefix minsim/s202 --broker tcp://127.0.0.1:1883 &
```

外部按 `client` 段（或 `scenario_id`）分流即可区分不同场景的态势。

---

## 7. 想定文件完整格式

> 想定 = 一份 JSON，回答：**世界里有哪些实体**（`entities`）、**每个实体由哪些组件拼成**（`archetypes` 模板 + 内联 `components`）、**每个组件参数是多少**。
> 想定里**不写规则**——规则由内核按"实体挂了哪些组件"自动匹配。

### 7.1 顶层结构

```json
{
  "name": "demo_area_defense",
  "version": "1.0",
  "simulation": { "step_seconds": 0.02, "speed_scale": 1.0, "max_duration_s": 120 },
  "world": { "origin": { "latitude_deg": 39.907, "longitude_deg": 116.391, "altitude_m": 50.0 } },
  "archetypes": { },
  "entities": [ ]
}
```

| 键 | 是否解析 | 说明 |
| --- | --- | --- |
| `name` | **是** | 想定名，最长 63 字符；随态势回传（`scenario_name`）。缺省取文件名 |
| `world.origin` | **是** | 地理参考原点（经纬高），位置字段据此换算；见 §7.2 |
| `archetypes` | **是** | 设备模板（组件静态清单），可缺省 |
| `entities` | **是** | 实体数组；缺失只告警、得到 0 个实体 |
| `version` | 否 | 保留字段，忽略 |
| `simulation` | 否 | **保留字段，当前忽略** |
| `_comment` / 其它 | 否 | 任意自定义键一律忽略 |

> **注意：`simulation` 段目前不生效。** 步长、倍速、最大步数只能由引擎命令行/配置文件设置（`--step-seconds` / `--speed` / `--steps`）。

### 7.2 地理坐标与参考原点

想定里**用经纬高写位置**，态势回传也是经纬高，换算由引擎完成。**参考原点优先级**（高 → 低）：

1. 想定 `world.origin`（若声明）；
2. 引擎命令行/配置文件的全局原点（`--origin-lat` / `--origin-lon` / `--origin-alt`）；
3. 都没有 → 局部模式，原点取 `(0,0,0)`（此时位置字段按局部 ENU 直读）。

> **建议**：生成想定时**总是写入 `world.origin`**，保证可复现、可正确换算。换算为 WGS-84 局部切平面线性近似：**距原点约 10 km 内误差 < 1 m**，适合单场景局部推演。

### 7.3 `archetypes`：设备模板

结构 `{ "模板名": ["组件名", ...] }`：

```json
"archetypes": {
  "quadrotor_uav": [
    "CompTransform", "CompFaction", "CompMotion",
    "CompRoute", "CompFlightModel", "CompUavRfLink", "CompUavHealth"
  ]
}
```

- 每个模板实例化为一个可复用模板；实体通过 `archetype` 引用并继承初值。
- 组件名必须与注册表一致（§7.9）；**未知组件名告警并跳过**，其余照常。
- 模板内同名组件自动去重，顺序无要求；该段可整体省略（改用纯内联写法）。

### 7.4 `entities`：实体

```json
{
  "name": "uav_quad_01",
  "archetype": "quadrotor_uav",
  "components": {
    "CompTransform": { "latitude_deg": 39.9042981, "longitude_deg": 116.39450838, "altitude_m": 50.0 },
    "CompFaction":   { "side": "blue" },
    "CompMotion":    { "speed_mps": 12.0, "heading_deg": 0.0, "mode": "ROUTE" },
    "CompFlightModel": { "platform": "quadrotor" },
    "CompRoute": {
      "accept_radius_m": 25.0,
      "waypoints": [ { "latitude_deg": 39.9051, "longitude_deg": 116.3965, "altitude_m": 110.0 } ]
    },
    "CompUavRfLink": { "gnss_locked": true, "rc_linked": true, "telemetry_linked": true },
    "CompUavHealth": { "hp": 100.0, "max_hp": 100.0 }
  }
}
```

| 键 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 否 | 实体名，最长 63 字符；随态势回传。缺省空串 |
| `archetype` | 否 | 引用模板名；**未知模板告警，实体退化为仅用内联 `components`** |
| `components` | 否 | 组件 → 字段对象，可**覆盖模板字段**、也可**追加模板外组件** |

解析行为要点：

- 同一实体重复出现同名组件：只保留一份，**按出现顺序反复覆盖字段**。
- 组件里的**未知键（拼错的字段名）被静默忽略**——不报错，极易踩坑。
- **携带 `CompFlightModel` 的实体会自动补 `CompFlightState`**（内部状态），想定**不要**写它。

### 7.5 字段默认值规则（重要）

组件结构在解析前被整体**清零**：

> **想定里没写的字段一律等于 `0`（或 `false`），而不是"工程默认值"。**

两个例外 / 陷阱：

1. **`CompFlightModel` 是唯一会回填默认值的组件**：只要写了 `platform`，其余字段若 `<= 0` 或未写，就填成该平台工程默认（§7.7）。所以飞行平台"只写 `platform` 也能飞"。
2. **布尔字段默认 `false`**，语义常为"关闭 / 失联 / 未锁定"。例如 `CompUavRfLink.gnss_locked` 留空即 `false` → 响应规则判导航失锁并进入 `FALLING`。**要正常飞行必须显式写 `true`。**

**结论：关键字段一律显式写全。**

### 7.6 坐标与角度约定（全局一致）

- 位置：**推荐经纬高** `latitude_deg` / `longitude_deg` / `altitude_m`（度/度/米）。
  - 兼容旧写法：`position_m: {x,y,z}`（局部 ENU，`x`=东, `y`=北, `z`=天），仅在无原点时使用。
  - 同时出现时**以经纬高为准**；都缺省记为 0。
  - 别名：`latitude_deg`↔`latitude`、`longitude_deg`↔`longitude`。
- 角度：单位**度**；`yaw_deg` 约定 **0 = 正北，顺时针为正**。
- 速度 m/s、频率 Hz、功率 W、增益 dBi。

### 7.7 组件参考

#### `CompTransform` 位姿

| 字段 | 类型 | 单位 | 留空 | 说明 |
| --- | --- | --- | --- | --- |
| `latitude_deg` | 数 | deg | 0 | 初始纬度，优先使用 |
| `longitude_deg` | 数 | deg | 0 | 初始经度，优先使用 |
| `altitude_m` | 数 | m | 0 | 初始海拔 |
| `position_m` | 对象 `{x,y,z}` | m | 0 | 兼容写法（局部 ENU），仅未给经纬高时生效 |
| `yaw_deg` / `pitch_deg` / `roll_deg` | 数 | deg | 0 | 初始姿态 |

> `altitude_m`（或 `position_m.z`）`<= 0.5 m` 视为"地面起步"：带飞行模型的实体首帧自动进入起飞相位。

#### `CompFaction` 阵营

| 字段 | 类型 | 取值 | 说明 |
| --- | --- | --- | --- |
| `side` | 字符串 | `"red"` / `"blue"` | **仅纯小写或纯大写**可识别；其它（含 `"Red"`、`"neutral"`）→ 中立(0) |

#### `CompMotion` 运动

| 字段 | 类型 | 单位 | 留空 | 说明 |
| --- | --- | --- | --- | --- |
| `speed_mps` | 数 | m/s | 0 | 指令速度；首帧锁定为巡航指令速度；`<=0` 用平台 `cruise_speed_mps` |
| `heading_deg` | 数 | deg | 0 | 航向（0=北，顺时针） |
| `climb_rate_mps` | 数 | m/s | 0 | 爬升率（仅 `CRUISE` 模式直接用） |
| `mode` | 字符串 | — | `IDLE` | 运动模式，见下 |

`mode` 取值（**区分大小写，仅接受全大写**，未匹配一律回退 `IDLE`）：

| 值 | 含义 |
| --- | --- |
| `IDLE` | 不动 |
| `CRUISE` | 定向定速：保持航向、按 `climb_rate_mps` 升降 |
| `ROUTE` | **沿 `CompRoute` 航路点飞行**（无人机常用） |
| `RETURN_HOME` | 返航到起飞点上方 |
| `LOST_LINK` / `FALLING` / `DESTROYED` | 失控 / 下坠 / 已摧毁，**由响应规则自动写入**，想定勿手填 |

> 想定能设的只有 `IDLE` / `CRUISE` / `ROUTE`；其余会被响应规则在运行时覆盖。

#### `CompRoute` 航路

| 字段 | 类型 | 单位 | 留空 | 说明 |
| --- | --- | --- | --- | --- |
| `accept_radius_m` | 数 | m | 0 | 到点判定半径；`<=0` 取默认 30 m |
| `loop` | 布尔 | — | `false` | 飞完末端是否回到第一个航路点循环 |
| `waypoints` | 数组 | — | 空 | 元素为 `{latitude_deg, longitude_deg, altitude_m}`（推荐）或 `{x,y,z}`（兼容）。**最多 16 个，超出告警丢弃** |

> 行为：依次飞向各点，进入 `accept_radius_m` 即推进下一个；全部飞完后带飞行模型的实体自动进近着陆（`loop=false`）。

#### `CompFlightModel` 飞行平台（无人机核心）

```json
"CompFlightModel": { "platform": "quadrotor" }
```

只写 `platform` 即用该平台默认参数，也可逐字段覆盖：

| 字段 | 类型 | 单位 | 说明 |
| --- | --- | --- | --- |
| `platform` | 字符串 | — | `"quadrotor"` / `"fixed_wing"` / `"fixed_wing_vtol"`（亦接受全大写）；其它 → 无模型（退化为点质量运动学） |
| `mass_kg` | 数 | kg | 质量 |
| `max_speed_mps` | 数 | m/s | 最大水平速度 / 空速上限 |
| `cruise_speed_mps` | 数 | m/s | 巡航速度 |
| `max_accel_mps2` | 数 | m/s² | 最大水平加速度 |
| `vertical_accel_mps2` | 数 | m/s² | 垂直最大加速度 |
| `max_climb_rate_mps` | 数 | m/s | 最大爬升率 |
| `max_descent_rate_mps` | 数 | m/s | 最大下降率 |
| `max_bank_deg` | 数 | deg | 最大滚转 / 侧倾 |
| `max_pitch_deg` | 数 | deg | 最大俯仰 |
| `max_yaw_rate_dps` | 数 | deg/s | 最大偏航角速度 |
| `stall_speed_mps` | 数 | m/s | 失速空速（固定翼专用） |
| `transition_speed_mps` | 数 | m/s | 旋翼↔机翼过渡空速（VTOL 专用） |
| `takeoff_alt_m` | 数 | m | 垂直起飞目标离地高度 |
| `drag_k` | 数 | — | 简化阻力系数 |
| `response_tau_s` | 数 | s | 速度/姿态一阶响应时间常数 |
| `bank_k` | 数 | — | 航向误差→滚转角增益（固定翼） |
| `speed_k` | 数 | — | 空速误差→推力增益（固定翼） |
| `climb_k` | 数 | — | 高度误差→爬升率增益 |

**三个平台默认参数**（未写或 `<=0` 时回填）：

| 字段 | quadrotor | fixed_wing | fixed_wing_vtol |
| --- | --- | --- | --- |
| `mass_kg` | 2.0 | 20.0 | 15.0 |
| `max_speed_mps` | 25.0 | 40.0 | 35.0 |
| `cruise_speed_mps` | 15.0 | 28.0 | 25.0 |
| `max_accel_mps2` | 4.0 | 2.0 | 3.0 |
| `vertical_accel_mps2` | 4.0 | 2.0 | 3.0 |
| `max_climb_rate_mps` | 6.0 | 8.0 | 6.0 |
| `max_descent_rate_mps` | 5.0 | 8.0 | 6.0 |
| `max_bank_deg` | 35.0 | 50.0 | 45.0 |
| `max_pitch_deg` | 30.0 | 20.0 | 20.0 |
| `max_yaw_rate_dps` | 120.0 | 60.0 | 60.0 |
| `stall_speed_mps` | 0.0 | 14.0 | 12.0 |
| `transition_speed_mps` | 0.0 | 0.0 | 16.0 |
| `takeoff_alt_m` | 30.0 | 40.0 | 50.0 |
| `drag_k` | 0.008 | 0.0016 | 0.0016 |
| `response_tau_s` | 0.6 | 0.8 | 0.8 |
| `bank_k` | 3.0 | 2.0 | 2.0 |
| `speed_k` | 1.5 | 1.0 | 1.0 |
| `climb_k` | 0.5 | 0.4 | 0.4 |

飞行相位机（`GROUND → TAKEOFF → ENROUTE → LANDING → DONE`）由内核自动推进，想定**无需声明**：`z ≈ 0` 起步自动起飞到 `takeoff_alt_m`；已在空中直接 `ENROUTE`；航路飞完进 `LANDING → DONE`。

#### `CompFlightState` 飞行动态状态（**只读，勿写**）

内核内部状态（相位、空速、油门、航迹倾角、着陆点），挂 `CompFlightModel` 时自动补齐，想定写它无意义。

#### `CompUavRfLink` 射频链路

| 字段 | 类型 | 留空 | 说明 |
| --- | --- | --- | --- |
| `gnss_locked` | 布尔 | `false` | 卫导锁定；`false` → 响应规则判 `FALLING` |
| `rc_linked` | 布尔 | `false` | 遥控在线；`false` → 判 `LOST_LINK` |
| `telemetry_linked` | 布尔 | `false` | 遥测在线 |
| `gnss_sir_db` | 数 | 0 | 卫导干信比 (dB) |
| `rc_sir_db` | 数 | 0 | 遥控干信比 (dB) |

> **默认全 `false`**。要正常飞行，必须显式 `gnss_locked: true` 且 `rc_linked: true`。

#### `CompUavHealth` 毁伤

| 字段 | 类型 | 留空 | 说明 |
| --- | --- | --- | --- |
| `hp` | 数 | 0 | 当前生命值 |
| `max_hp` | 数 | 0 | 最大生命值 |
| `damage` | 数 | 0 | 累计损伤 |
| `destroyed` | 布尔 | `false` | 是否已摧毁；`true` → 判 `DESTROYED` |

> 判定只看 `destroyed` 布尔，不看 `hp`。但为态势显示正常，建议写 `hp = max_hp = 100`。

#### `CompUavSensor` 机载光电/红外

| 字段 | 类型 | 留空 | 说明 |
| --- | --- | --- | --- |
| `eo_available` | 布尔 | `false` | 光电可用 |
| `ir_available` | 布尔 | `false` | 红外可用 |
| `blindness` | 数 | 0 | 致盲度：0 正常，1 完全致盲 |

#### 反制设备组件（效应规则当前为占位实现）

> 这些组件可解析并挂载，但对应效应规则**大多仍是占位实现，不产生实际对抗效果**。可先建模，但不要依赖反制效果。

| 组件 | 字段 |
| --- | --- |
| `CompJammerEmitter` | `enabled`(bool) `freq_hz` `power_w` `gain_dbi` `bandwidth_hz`（作用距离由功率反推，无独立距离字段） |
| `CompRadarSensor` | `enabled`(bool) `freq_hz` `power_w` `gain_dbi` `max_range_m` `min_rcs_m2` |
| `CompLaserEmitter` | `enabled`(bool) `power_w` `wavelength_nm` `divergence_mrad` `max_range_m` |
| `CompRadarObservation` | `detected`(bool) `range_m` `snr_db` `last_seen_tick`（**运行态，一般不在想定里写**） |

### 7.8 推荐模板（设备类型 → 组件组合）

| 设备 | 组件组合 | 说明 |
| --- | --- | --- |
| 侦察无人机 | `CompTransform` `CompFaction` `CompMotion` `CompRoute` `CompUavRfLink` `CompUavSensor` `CompUavHealth` | 点到点航路（无飞行动力学） |
| **四旋翼无人机** | `CompTransform` `CompFaction` `CompMotion` `CompRoute` **`CompFlightModel`** `CompUavRfLink` `CompUavHealth` | 起降 + 航路 + 3-DOF 动力学 |
| **VTOL 无人机** | 同上，`platform = "fixed_wing_vtol"` | 垂直起降 + 过渡巡航 |
| 干扰站 / 雷达站 / 激光站 | `CompTransform` `CompFaction` `Comp{Jammer|Radar|Laser}Emitter/Sensor` | 固定地面设备 |

### 7.9 组件名速查（注册表顺序即组件 id，勿随意调整）

```
CompTransform, CompMotion, CompFaction, CompRoute,
CompJammerEmitter, CompRadarSensor, CompLaserEmitter,
CompUavRfLink, CompUavSensor, CompUavHealth,
CompRadarObservation, CompFlightModel, CompFlightState
```

### 7.10 示例

**最小可飞想定（单架四旋翼自动起降）**

```json
{
  "name": "one_quad",
  "world": { "origin": { "latitude_deg": 39.907, "longitude_deg": 116.391, "altitude_m": 50.0 } },
  "entities": [
    {
      "name": "uav_01",
      "components": {
        "CompTransform":   { "latitude_deg": 39.907, "longitude_deg": 116.391, "altitude_m": 50.0 },
        "CompFaction":     { "side": "blue" },
        "CompMotion":      { "speed_mps": 12.0, "mode": "ROUTE" },
        "CompFlightModel": { "platform": "quadrotor" },
        "CompRoute": {
          "accept_radius_m": 25.0,
          "loop": false,
          "waypoints": [
            { "latitude_deg": 39.90880, "longitude_deg": 116.391, "altitude_m": 110.0 },
            { "latitude_deg": 39.90880, "longitude_deg": 116.38870, "altitude_m": 110.0 }
          ]
        },
        "CompUavRfLink": { "gnss_locked": true, "rc_linked": true, "telemetry_linked": true },
        "CompUavHealth": { "hp": 100.0, "max_hp": 100.0 }
      }
    }
  ]
}
```

行为：地面自动起飞到 30 m → 飞两个航路点 → 进近着陆 → 停住。

**带设备模板的完整想定**：完整可运行样例见仓库 [scenarios/demo_scenario.json](file:///d:/zky-project/gitlib/minsim/scenarios/demo_scenario.json)，演示 `archetypes` 模板 + `entities` 覆盖写法，包含侦察机、四旋翼、VTOL、干扰站、雷达站、激光站。

可用 `sim scenario example` 打印一份最小可用想定，`sim scenario check <文件>` 校验想定。

### 7.11 常见坑（可据此做前端校验）

| 现象 | 原因 |
| --- | --- |
| 实体不动 | `CompMotion.mode` 写成小写（`"route"`）→ 回退 `IDLE`；或没挂 `CompRoute` |
| 无人机一起飞就坠落 | `CompUavRfLink` 留空 → `gnss_locked=false` → 判 `FALLING` |
| `side` 显示中立 | `"Red"` / `"BLUE "` 等不匹配，只认纯 `red`/`blue`（或纯大写） |
| 设了 `simulation.step_seconds` 无效 | 该段当前不解析，需用引擎命令行/配置设置 |
| 航路点只飞了前 16 个 | 上限 16，多余被丢弃 |
| 字段写了没反应 | 字段名拼错被静默忽略 |
| 上传后没跑起来 | 引擎未用 `serve`；或会话数已达上限（收 `1001`，需 `/admin` 扩容）；JSON 不合法 |

---

## 8. 端到端交互时序

**默认会话（单客户端）**

```
外部客户端                                       minsim 引擎 (serve)
   │                                                    │
   │  connect  ws://broker:8083                          │
   │  subscribe  minsim/telemetry                        │
   │  subscribe  minsim/event                            │
   │                                                    │
   │  publish  minsim/scenario  { 想定 JSON }  ─────────▶ 解析 → 实例化 → 自动开跑
   │                                                    │
   │  ◀────────  publish  minsim/telemetry  (每步一条)   │
   │  ◀────────  publish  minsim/telemetry               │
   │                                                    │
   │  publish  minsim/command  {"action":"pause"}  ─────▶ 暂停
   │  publish  minsim/command  {"action":"speed","value":4} ▶ 4 倍速
   │  publish  minsim/command  {"action":"resume"} ─────▶ 恢复
   │                                                    │
   │  publish  minsim/command  {"action":"stop"}   ─────▶ 结束当前场景
   │                                                    │
   │  publish  minsim/scenario  { 下一份想定 }     ─────▶ 新场景（scenario_id +1）
```

**多客户端并发（每会话一条独立推演线程）**

```
客户端 A (client=uav01)                      minsim 引擎 (serve)
   │  publish  minsim/uav01/scenario  ───────▶ 新会话 uav01 → 实例化 → 开跑（线程 1）
   │  ◀────────  minsim/uav01/telemetry         │
   │  publish  minsim/uav01/command            │ 仅作用于 uav01
   │  publish  minsim/uav01/scenario (重发) ──▶ 先停 uav01 → 再起新想定
   │                                           │
客户端 B (client=uav02)                        │
   │  publish  minsim/uav02/scenario  ───────▶ 新会话 uav02 → 实例化 → 开跑（线程 2）
   │  ◀────────  minsim/uav02/telemetry         │
   │                                           │
客户端 C (超限, 已满 32)                        │
   │  publish  minsim/uav33/scenario  ───────▶ 拒绝；◀─ minsim/uav33/event {code:1001}
   │  publish  minsim/admin  {"action":"capacity","value":64} ──▶ 上限提升到 64
   │  publish  minsim/uav33/scenario  ───────▶ 接受 → 开跑
```

**前端页面建议包含的功能区**

| 区域 | 职责 | 数据来源 |
| --- | --- | --- |
| **连接状态栏** | broker 连接/断开、当前 `scenario_name` / `scenario_id` / `tick` / `sim_time_s` | telemetry 顶层字段 |
| **想定编排面板** | 构造 `entities`，写入 `world.origin`，导出 JSON 并上传 | 上行 `<prefix>/scenario` |
| **态势地图** | 按经纬高绘制实体；按 `side` 上色，按 `motion_mode` 换图标；显示 `altitude_m`；画轨迹 | telemetry `entities[]` |
| **实体列表 / 详情** | 名称、阵营、速度、姿态、`hp`、链路状态、SIR | telemetry `entities[]` |
| **控制条** | 暂停 / 恢复 / 停止 / 倍速 | 上行 `<prefix>/command` |
| **告警面板** | 从态势字段推断异常；订阅 `<prefix>/<client>/event` 处理事件码 | telemetry 字段 / event |

**关键实现要点**

1. **必须用 MQTT over WebSocket**（浏览器环境），指向 broker 的 WS 端口。
2. **态势是 50 Hz 全量推送**（默认步长 0.02 s）。UI 渲染**务必节流**（如 `requestAnimationFrame` 合并，或降频到 10–20 Hz）。
3. **无 retained**：连上后从**下一帧**开始才有数据；断线重连会丢历史，需自己维护实体状态表并容忍跳变。
4. **以 `client` 段（或 `scenario_id`）分流**：多客户端/多场景并存时按它隔离状态（见 §4.4）。
5. **`id` 只保证单次运行内唯一**，不要跨运行持久化。
6. **控制指令严格用 `{"action":"...","value":N}` 形态**（键名带双引号、全小写），`speed` 的 `value` 必须 > 0。
7. **不要做坐标换算**：拿到的就是经纬高，直接喂给地图库。
8. **异常兜底**：`reported_count < entity_count` 或收到 `truncated:true` 时提示"态势被截断"，不要当成数组为空而崩溃。
9. **切换场景**：可先 `stop` 结束当前再上传新想定；同 `client` 重传则会**先停后起**。

---

## 9. 客户端示例

> 下列示例均以**默认会话**（无 `client` 段）演示。需要多客户端并发时，把主题中的 `<prefix>/` 换成 `<prefix>/<client>/` 即可（如 `minsim/uav01/telemetry`），详见 §4.4。

### 9.1 mosquitto 命令行（便于自测）

```bash
# 观察态势
mosquitto_sub -h 10.5.23.205 -p 1883 -t 'minsim/telemetry' -v
# 上传想定
mosquitto_pub -h 10.5.23.205 -p 1883 -t 'minsim/scenario' -f scenarios/demo_scenario.json
# 控制
mosquitto_pub -h 10.5.23.205 -p 1883 -t 'minsim/command' -m '{"action":"pause"}'
mosquitto_pub -h 10.5.23.205 -p 1883 -t 'minsim/command' -m '{"action":"speed","value":4}'
mosquitto_pub -h 10.5.23.205 -p 1883 -t 'minsim/command' -m '{"action":"stop"}'
# 具名会话（多客户端）
mosquitto_sub -h 10.5.23.205 -p 1883 -t 'minsim/uav01/telemetry' -v
mosquitto_pub -h 10.5.23.205 -p 1883 -t 'minsim/uav01/scenario' -f scenarios/demo_scenario.json
# 运行期扩容会话上限
mosquitto_pub -h 10.5.23.205 -p 1883 -t 'minsim/admin' -m '{"action":"capacity","value":64}'
```

> broker 要求认证时，加 `-u <user> -P <pass>`。

### 9.2 Python (paho-mqtt)

```python
import json
import paho.mqtt.client as mqtt

PREFIX = "minsim"

def on_connect(client, userdata, flags, rc, properties=None):
    client.subscribe(f"{PREFIX}/telemetry", qos=1)
    client.subscribe(f"{PREFIX}/event", qos=1)

def on_message(client, userdata, msg):
    payload = json.loads(msg.payload)
    if payload.get("type") == "telemetry":
        print(f"[tick {payload['tick']}] 实体 {payload['reported_count']} 个")
        for e in payload["entities"]:
            print(f"  {e['name']}: lat={e['latitude_deg']} lon={e['longitude_deg']} "
                  f"alt={e['altitude_m']} mode={e['motion_mode']}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="minsim-viewer")
client.on_connect = on_connect
client.on_message = on_message
# broker 要求认证时: client.username_pw_set("JavaServer", "123456")
client.connect("10.5.23.205", 1883, keepalive=30)
client.loop_start()

# 上传想定：把 JSON 字符串原样发到 scenario 主题
with open("scenarios/demo_scenario.json", "r", encoding="utf-8") as fp:
    client.publish(f"{PREFIX}/scenario", fp.read(), qos=1)

# 运行中控制
client.publish(f"{PREFIX}/command", json.dumps({"action": "speed", "value": 2.0}), qos=1)
```

### 9.3 浏览器参考实现（MQTT.js + Leaflet）

```js
import mqtt from "mqtt";
import L from "leaflet";

const PREFIX = "minsim";
const BROKER = "ws://10.5.23.205:8083";   // 指向 broker 的 WebSocket 端口

// 1) 建图
const map = L.map("map").setView([39.907, 116.391], 13);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(map);

// 2) 连 MQTT
const client = mqtt.connect(BROKER, {
  clientId: "minsim-frontend-" + Math.random().toString(16).slice(2, 8),
  clean: true,
  keepalive: 30,
});

client.on("connect", () => {
  client.subscribe(`${PREFIX}/telemetry`, { qos: 1 });
  client.subscribe(`${PREFIX}/event`, { qos: 1 });
});

// 3) 实体状态表 + 节流渲染
const markers = new Map();     // id -> L.Marker
let pending = null;            // 最新一帧（渲染前只保留最后一帧）

client.on("message", (topic, payload) => {
  let msg;
  try { msg = JSON.parse(payload.toString()); } catch { return; }

  if (topic === `${PREFIX}/telemetry`) {
    if (msg.truncated) return;          // 整条被截断，跳过
    pending = msg;                      // 只留最后一帧
  } else if (topic === `${PREFIX}/event`) {
    console.log("event", msg);          // 引擎当前不产生事件，逻辑先预留
  }
});

function render() {
  const frame = pending;
  if (frame) {
    pending = null;
    for (const e of frame.entities) {
      const latlng = [e.latitude_deg, e.longitude_deg];
      let m = markers.get(e.id);
      if (!m) {
        m = L.marker(latlng, { icon: iconFor(e) }).addTo(map);
        markers.set(e.id, m);
      } else {
        m.setLatLng(latlng);
      }
      m.bindTooltip(
        `${e.name} | alt=${e.altitude_m.toFixed(1)}m | ` +
        `mode=${MODE_NAME[e.motion_mode]} | hp=${e.hp}`
      );
    }
  }
  requestAnimationFrame(render);        // 50Hz 输入 → 帧同步渲染，避免卡顿
}
requestAnimationFrame(render);

const MODE_NAME = ["IDLE","CRUISE","LOST_LINK","FALLING","RETURN_HOME","DESTROYED","ROUTE"];
const SIDE_COLOR = { 0: "#9e9e9e", 1: "#e53935", 2: "#1e88e5" };  // 中立/红/蓝

function iconFor(e) {
  return L.divIcon({
    className: "",
    html: `<div style="width:12px;height:12px;border-radius:50%;
           background:${SIDE_COLOR[e.side] ?? "#9e9e9e"};
           border:2px solid #fff"></div>`,
  });
}

// 4) 控制指令
function sendCommand(action, value) {
  // 注意：必须是 {"action":"xxx"} 形态，键名带双引号且全小写
  client.publish(`${PREFIX}/command`, JSON.stringify({ action, value }), { qos: 1 });
}

// 5) 上传想定
function uploadScenario(scenarioObj) {
  client.publish(`${PREFIX}/scenario`, JSON.stringify(scenarioObj), { qos: 1 });
}
uploadScenario({
  name: "one_quad",
  world: { origin: { latitude_deg: 39.907, longitude_deg: 116.391, altitude_m: 50.0 } },
  entities: [{
    name: "uav_01",
    components: {
      CompTransform:   { latitude_deg: 39.907, longitude_deg: 116.391, altitude_m: 50.0 },
      CompFaction:     { side: "blue" },
      CompMotion:      { speed_mps: 12.0, mode: "ROUTE" },
      CompFlightModel: { platform: "quadrotor" },
      CompRoute: { accept_radius_m: 25.0, waypoints: [
        { latitude_deg: 39.9088, longitude_deg: 116.391, altitude_m: 110.0 }
      ]},
      CompUavRfLink: { gnss_locked: true, rc_linked: true, telemetry_linked: true },
      CompUavHealth: { hp: 100.0, max_hp: 100.0 }
    }
  }]
});
```

---

## 10. 限制与注意事项

| 项 | 说明 |
| --- | --- |
| 认证 | 支持**用户名/密码**（`--username` / `--password`）；**不支持 TLS/SSL**，请仅在受信网络内使用 |
| retained / LWT | 未使用；连上后不会收到历史态势，须等下一帧 |
| 事件通路 | 报文格式已定义，**内核暂不产生业务事件**；网络层的会话超限事件 `1001` 已可用 |
| 态势实体上限 | 单帧最多 **256** 个实体，超出被截断 |
| 态势报文上限 | **131072 字节（128 KB）**，超出则发 `truncated` 占位报文 |
| 想定缓存 | **每会话**只保留最近一份，重复上传覆盖未取用的那份 |
| 想定生效时机 | 需 `serve`；同会话重传会**先停旧再起新**，无需手动 `stop` |
| 想定受理回执 | **无**，只能靠新 `scenario_id` 的态势判断是否跑起来 |
| 场景时长 | 由引擎 `--steps` 决定，**想定 `simulation` 段不生效** |
| 控制粒度 | 仅场景级（start/pause/resume/stop/speed），**无单实体指令**；指令作用于收到它的会话 |
| 坐标系 | 对外统一 WGS-84 经纬高，引擎负责换算，使用方无需处理原点 |
| 多客户端并发 | **单进程多会话**（最多 32，`/admin` 可扩容），按主题 `client` 段隔离；另可用多进程 |
| 会话隔离 | 每会话独立原点、想定实例、队列与推演线程，互不干扰 |
| 背压策略 | 网络慢时下行队列（容量 256）满则**丢弃新态势**并计数，推演不受影响 |
| 反制效应 | 干扰→失控链路已实现；**激光致盲 / 武器毁伤 / 雷达探测规则仍为占位实现**，无实际对抗效果 |
| 返航归航 | `RETURN_HOME` 当前按巡航速度直线飞行，不朝原点归航 |

### 当前能力状态（速览）

| 能力 | 状态 |
| --- | --- |
| 想定解析 + 实体实例化、设备模板 `archetypes` | 已实现 |
| 运动积分（IDLE/CRUISE/LOST_LINK/FALLING/DESTROYED/ROUTE） | 已实现 |
| 沿航路点飞行 `CompRoute` | 已实现 |
| 飞行动力学：四旋翼 / 固定翼 / VTOL | 已实现 |
| 干扰效应 → SIR → 链路状态、无人机响应 | 已实现 |
| MQTT 网络层、态势/事件/指令 JSON、想定上传、常驻服务 | 已实现 |
| 单进程多客户端并发（最多 32 路，`/admin` 可扩容，会话隔离） | 已实现 |
| 激光致盲 / 武器毁伤 / 雷达探测效应 | **占位（空函数）** |
| 组件级控制指令（开关设备/调参） | **未实现** |
| 业务事件产生（除会话超限 `1001`） | **未实现** |

---

## 11. 排障

| 现象 | 排查方向 |
| --- | --- |
| 收不到任何态势 | 看启动日志是否出现 `MQTT 已连接`；没有则检查 broker 地址 / 网络 / `client_id` 冲突 |
| 日志出现"降级模式运行" | `broker` 为空，未建链；补上 `--broker` 或配置文件 `broker` |
| 上传想定无反应 | 是否以 `serve` 启动；会话数是否已达上限（订阅 `<prefix>/<client>/event` 看是否收到 `1001`）；载荷是否为合法想定 JSON |
| 指令不生效 | 载荷是否含 `"action":"xxx"`（键名带双引号、全小写）；`speed` 的 `value` 是否 > 0 |
| 连接反复失败 | 查看引擎日志中的 `rc=` 返回码与重试记录（每 2 秒重试）；确认 broker 是否允许 WebSocket（若用 `ws://`）；确认用户名/密码 |
| 浏览器连不上 broker | 浏览器需 WebSocket 端口；确认 broker 已开 WS 监听（如 8083） |
| 地图上实体不动/闪 | 是否每帧重渲染；请按 §8 节流 |
| 页面刷新后长时间空白 | 引擎无 retained，刷新后需等下一帧（若引擎在跑应立刻出） |
| 退出时统计 | 引擎停止日志打印：已发布 / 已接收指令 / 收到想定 / 发送失败 / 下行丢弃 / 连接失败 |

---

## 12. 关键常量速查

| 名称 | 值 | 含义 |
| --- | --- | --- |
| 默认主题前缀 | `minsim` | 主题 = `<前缀>/telemetry` 等；具名会话 = `<前缀>/<client>/...` |
| 默认并发会话上限 | `32` | 具名会话数上限，`/admin` 可扩容（只增不减） |
| 会话超限事件码 | `1001` | 发至触发者 `<prefix>/<client>/event` |
| 默认步长 | `0.02 s` | 50 Hz 态势频率（由引擎 `--step-seconds` 决定） |
| 默认端口示例 | `1883`(tcp) / `8083`(ws) | broker 端口，以实际部署为准 |
| 单帧实体上限 | `256` | 超出被截断 |
| 单条报文上限 | `131072` 字节 | 超出整条变 `{"truncated":true}` |
| 航路点上限 | `16` | 超出丢弃 |
| `side` | `0/1/2` | 中立/红方/蓝方 |
| `motion_mode` | `0..6` | IDLE/CRUISE/LOST_LINK/FALLING/RETURN_HOME/DESTROYED/ROUTE |
| `platform` | `quadrotor` / `fixed_wing` / `fixed_wing_vtol` | 飞行平台 |
| 指令 action | `start` `pause` `resume` `stop` `speed` | 场景级控制 |
| 组件名 | 见 §7.9 | 想定 `archetypes` / `components` 的键 |
