"""血缘关系语义注册表。

改造方案 §7.1：为每种关系定义「原始端点存储方向 → 真实数据流向、中文正/反向文案、
是否参与影响传播、允许的证据来源」。布局、遍历与路径解释必须共用同一套规则，
否则会把数据库出边误当下游（reads/writes/derives_from 的存储方向与数据流方向并不总是一致）。

真实写入来源（见 lineage_service）：
- binds_to      asset → object_type（ObjectBinding 配置供数）
- reads         asset → object_type（执行记录：某用途读取，累加权重）
- writes        object_type → asset（行动/函数回写，规划中）
- derives_from  target(产物) → source(来源)（推导关系，数据流与存储方向相反）
"""
from __future__ import annotations

# 每种关系的语义定义：
#   flow:  "forward"=存储 source→target 即数据流方向；"reverse"=存储方向与数据流相反
#   zh_from / zh_to: 沿数据流方向阅读时的中文连线文案（正向/反向表述）
#   impact: 是否参与影响传播（配置元数据关联可不参与）
#   evidence: 该关系默认依据来源 config（配置）/ execution（执行）/ inference（推导）
RELATION_SEMANTICS: dict[str, dict] = {
    "binds_to": {
        "flow": "forward",
        "zh_from": "字段映射",
        "zh_to": "被字段映射",
        "impact": True,
        "evidence": "config",
        "explain": "{src} 通过字段映射向 {tgt} 供数。",
    },
    "reads": {
        "flow": "forward",
        "zh_from": "供数读取",
        "zh_to": "读取自",
        "impact": True,
        "evidence": "execution",
        "explain": "{tgt} 在执行中读取 {src} 的数据。",
    },
    "writes": {
        "flow": "forward",
        "zh_from": "写入",
        "zh_to": "被写入",
        "impact": True,
        "evidence": "execution",
        "explain": "{src} 将处理结果写入 {tgt}。",
    },
    "derives_from": {
        "flow": "reverse",
        "zh_from": "加工生成",
        "zh_to": "经加工来源于",
        "impact": True,
        "evidence": "inference",
        "explain": "{src} 经过加工生成 {tgt}。",
    },
}


def flow_endpoints(relation: str, source: tuple[str, str], target: tuple[str, str]) -> tuple[tuple[str, str], tuple[str, str]]:
    """把「存储端点」归一为「数据流端点」(flow_from, flow_to)。

    reverse 语义（如 derives_from）存储为 产物→来源，但数据流是 来源→产物，需翻转。
    """
    sem = RELATION_SEMANTICS.get(relation)
    if sem and sem["flow"] == "reverse":
        return target, source
    return source, target


def zh_label(relation: str, forward: bool = True) -> str:
    """连线中文文案。forward=True 沿数据流方向阅读，False 反向。"""
    sem = RELATION_SEMANTICS.get(relation)
    if not sem:
        return relation
    return sem["zh_from"] if forward else sem["zh_to"]


def participates_in_impact(relation: str) -> bool:
    sem = RELATION_SEMANTICS.get(relation)
    return bool(sem["impact"]) if sem else True


def evidence_of(relation: str) -> str:
    sem = RELATION_SEMANTICS.get(relation)
    return sem["evidence"] if sem else "config"


# 节点类型中文文案（改造方案 §3.1 术语对照）
KIND_LABEL_ZH: dict[str, str] = {
    "asset": "数据资产",
    "object_type": "业务对象",
    "action": "业务行动",
    "rule": "业务规则",
}

# 依据来源中文文案（§6.1）
EVIDENCE_LABEL_ZH: dict[str, str] = {
    "config": "配置依据",
    "execution": "执行记录",
    "inference": "推导关系",
    "pending": "待确认",
}
