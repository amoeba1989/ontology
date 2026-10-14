from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DraftAttribute(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,59}$")
    label: str = Field(min_length=1, max_length=100)
    type: Literal["string", "number", "boolean", "date", "json"] = "string"
    required: bool = False
    unit: str = Field(default="", max_length=50)
    description: str = Field(default="", max_length=2000)


class DraftEntity(StrictModel):
    name: str = Field(pattern=r"^[A-Z][A-Za-z0-9]{0,79}$")
    label: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    reuse_id: str | None = None
    attributes: list[DraftAttribute] = Field(default_factory=list, max_length=100)


class DraftRelation(StrictModel):
    name: str = Field(pattern=r"^[a-z][A-Za-z0-9]{0,79}$")
    label: str = Field(default="", max_length=50)
    source: str
    target: str
    cardinality: Literal["1:1", "1:N", "N:1", "N:N"] = "N:N"


class RuleClause(StrictModel):
    field: str
    operator: Literal["required", "eq", "ne", "gt", "gte", "lt", "lte", "in"]
    value: Any = None


class RuleExample(StrictModel):
    label: str = Field(default="", max_length=100)
    values: dict = Field(default_factory=dict)
    expected: bool


class DraftRule(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    entity: str
    kind: Literal["structure", "common", "business"] = "business"
    origin: Literal["ai", "manual", "template"] = "manual"
    basis: str = Field(default="", max_length=2000)
    assumptions: str = Field(default="", max_length=2000)
    exceptions: str = Field(default="", max_length=2000)
    confirmed: bool = False
    status: Literal["pending", "accepted", "rejected"] = "pending"
    clauses: list[RuleClause] = Field(default_factory=list, max_length=20)
    examples: list[RuleExample] = Field(default_factory=list, max_length=20)


class DraftContent(StrictModel):
    entities: list[DraftEntity] = Field(default_factory=list, max_length=50)
    relations: list[DraftRelation] = Field(default_factory=list, max_length=150)
    rules: list[DraftRule] = Field(default_factory=list, max_length=100)
    questions: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def valid_references(self):
        entities = {e.name: e for e in self.entities}
        if len(entities) != len(self.entities):
            raise ValueError("对象英文标识不可重复")
        for e in self.entities:
            if len({a.name for a in e.attributes}) != len(e.attributes):
                raise ValueError(f"{e.name} 的属性标识重复")
        if len({r.id for r in self.rules}) != len(self.rules):
            raise ValueError("规则编号不可重复")
        for r in self.relations:
            if r.source not in entities or r.target not in entities:
                raise ValueError("关系引用了不存在的对象")
        if len({(r.source, r.target, r.name) for r in self.relations}) != len(self.relations):
            raise ValueError("关系重复")
        for rule in self.rules:
            if rule.entity not in entities:
                raise ValueError("规则引用了不存在的对象")
            attrs = {a.name: a for a in entities[rule.entity].attributes}
            for clause in rule.clauses:
                if clause.field not in attrs:
                    raise ValueError(f"规则 {rule.name} 引用了不存在的属性 {clause.field}")
                if clause.operator in ("gt", "gte", "lt", "lte") and (attrs[clause.field].type != "number" or type(clause.value) not in (int, float)):
                    raise ValueError("大小比较必须使用数值属性及数值阈值")
                if clause.operator == "in" and not isinstance(clause.value, list):
                    raise ValueError("in 操作符需要数组阈值")
        return self


class DraftWrite(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    scenario: str = Field(default="", max_length=12000)
    content: DraftContent = Field(default_factory=DraftContent)
    revision: int = Field(default=1, ge=1)


class RevisionRequest(StrictModel):
    revision: int = Field(ge=1)
