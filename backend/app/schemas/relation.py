from typing import Literal

from pydantic import BaseModel, model_validator

RelType = Literal["has_one", "has_many", "belongs_to", "many_to_many"]
Cardinality = Literal["1:1", "1:N", "N:1", "N:N"]

CARDINALITY_OF_REL_TYPE: dict[str, str] = {
    "has_one": "1:1",
    "has_many": "1:N",
    "belongs_to": "N:1",
    "many_to_many": "N:N",
}


class RelationCreate(BaseModel):
    from_entity_id: str
    to_entity_id: str
    name: str
    name_cn: str | None = None
    rel_type: RelType = "has_many"
    cardinality: Cardinality = "1:N"
    description: str | None = None

    @model_validator(mode="after")
    def rel_type_matches_cardinality(self) -> "RelationCreate":
        expected = CARDINALITY_OF_REL_TYPE[self.rel_type]
        if self.cardinality != expected:
            raise ValueError(
                f"cardinality must be {expected!r} for rel_type {self.rel_type!r}, got {self.cardinality!r}"
            )
        return self


class RelationOut(BaseModel):
    id: str
    from_entity_id: str
    from_entity_name: str
    to_entity_id: str
    to_entity_name: str
    name: str
    name_cn: str | None = None
    rel_type: str
    cardinality: str
    description: str | None
