from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class FieldType(str, Enum):
    string = "string"
    text = "text"
    integer = "integer"
    float_ = "float"
    boolean = "boolean"
    datetime = "datetime"
    uuid = "uuid"
    json = "json"

    @classmethod
    def _missing_(cls, value: object) -> None:
        valid = [e.value for e in cls]
        raise ValueError(f"Unknown field type '{value}'. Valid types: {valid}")


class RelationType(str, Enum):
    one_to_one = "one-to-one"
    one_to_many = "one-to-many"
    many_to_one = "many-to-one"
    many_to_many = "many-to-many"


class FieldSchema(BaseModel):
    name: str
    type: FieldType
    primary_key: bool = False
    unique: bool = False
    nullable: bool = True
    length: int | None = None
    default: Any | None = None
    index: bool = False
    description: str | None = None
    foreign_key: str | None = None  # e.g. "users.id"

    @field_validator("length")
    @classmethod
    def length_only_for_string(cls, v: int | None, info: Any) -> int | None:
        if v is not None and info.data.get("type") not in (FieldType.string, "string"):
            raise ValueError("'length' is only valid for string fields")
        return v


class RelationSchema(BaseModel):
    name: str
    type: RelationType
    target_model: str
    back_populates: str | None = None


class ModelSchema(BaseModel):
    model_name: str = Field(..., pattern=r"^[A-Z][A-Za-z0-9]*$")
    table_name: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    description: str | None = None
    auth_required: bool = False
    fields: list[FieldSchema]
    relations: list[RelationSchema] = []

    @field_validator("fields")
    @classmethod
    def must_have_primary_key(cls, v: list[FieldSchema]) -> list[FieldSchema]:
        if not any(f.primary_key for f in v):
            raise ValueError("Blueprint must define at least one primary_key field")
        return v
