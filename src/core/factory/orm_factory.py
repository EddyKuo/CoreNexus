from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship

from src.core.models.schema_def import FieldSchema, FieldType, ModelSchema, RelationType

# Abstract type → SQLAlchemy column type
_SA_TYPE_MAP: dict[FieldType, Any] = {
    FieldType.string: String,
    FieldType.text: Text,
    FieldType.integer: Integer,
    FieldType.float_: Float,
    FieldType.boolean: Boolean,
    FieldType.datetime: DateTime(timezone=True),
    FieldType.uuid: Uuid,
    FieldType.json: JSON,
}


def _build_sa_column(field: FieldSchema) -> Any:
    sa_type = _SA_TYPE_MAP[field.type]

    if field.type == FieldType.string and field.length:
        sa_type = String(length=field.length)

    kwargs: dict[str, Any] = {
        "primary_key": field.primary_key,
        "nullable": field.nullable,
        "unique": field.unique,
        "index": field.index,
    }

    if field.default is not None:
        if field.default == "uuid4":
            kwargs["default"] = uuid.uuid4
        elif field.default == "now":
            kwargs["server_default"] = func.now()
        else:
            kwargs["default"] = field.default
    elif field.type == FieldType.uuid and field.primary_key:
        kwargs["default"] = uuid.uuid4

    if field.foreign_key:
        return mapped_column(sa_type, ForeignKey(field.foreign_key), **kwargs)

    return mapped_column(sa_type, **kwargs)


def create_orm_model(schema: ModelSchema, Base: type[DeclarativeBase]) -> type:
    """Dynamically create a SQLAlchemy ORM model from a ModelSchema.

    If a class with the same model_name is already registered on this Base,
    the existing class is returned unchanged (idempotent).
    """
    # Return cached class to avoid "Table already defined" on re-import / test re-runs
    existing = Base.registry._class_registry.get(schema.model_name)
    if existing is not None:
        return existing

    attrs: dict[str, Any] = {
        "__tablename__": schema.table_name,
        # Allow the table to be redefined if it already exists in metadata
        "__table_args__": {"extend_existing": True},
    }

    for field in schema.fields:
        attrs[field.name] = _build_sa_column(field)

    # Phase 1 relations (forward references are strings — resolved after all models exist)
    for rel in schema.relations:
        rel_kwargs: dict[str, Any] = {}
        if rel.back_populates:
            rel_kwargs["back_populates"] = rel.back_populates
        if rel.type == RelationType.one_to_many:
            rel_kwargs["lazy"] = "select"
        attrs[rel.name] = relationship(rel.target_model, **rel_kwargs)

    model_cls = type(schema.model_name, (Base,), attrs)
    return model_cls


def build_all_orm_models(
    schemas: list[ModelSchema], Base: type[DeclarativeBase]
) -> dict[str, type]:
    """Create ORM models for all schemas and return a name→class mapping."""
    return {schema.model_name: create_orm_model(schema, Base) for schema in schemas}
