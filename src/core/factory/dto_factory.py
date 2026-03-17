from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, create_model, Field

from src.core.models.schema_def import FieldSchema, FieldType, ModelSchema

# Abstract type → Python/Pydantic type
_PYDANTIC_TYPE_MAP: dict[FieldType, type] = {
    FieldType.string: str,
    FieldType.text: str,
    FieldType.integer: int,
    FieldType.float_: float,
    FieldType.boolean: bool,
    FieldType.datetime: datetime,
    FieldType.uuid: uuid.UUID,
    FieldType.json: dict | list,
}


def _generate_example(field: FieldSchema) -> Any:
    if field.type == FieldType.string:
        name = field.name.lower()
        if "email" in name: return "user@example.com"
        if "url" in name or "link" in name: return "https://example.com"
        if "phone" in name: return "+886912345678"
        if "name" in name: return "Example Name"
        if "status" in name: return "active"
        return "string_value"
    elif field.type == FieldType.text:
        return "Detailed text content goes here..."
    elif field.type == FieldType.integer:
        if "price" in field.name.lower() or "amount" in field.name.lower(): return 100
        return 42
    elif field.type == FieldType.float_:
        return 99.99
    elif field.type == FieldType.boolean:
        return True
    elif field.type == FieldType.datetime:
        return "2026-12-31T23:59:59Z"
    elif field.type == FieldType.uuid:
        return "123e4567-e89b-12d3-a456-426614174000"
    elif field.type == FieldType.json:
        return {"key": "value"}
    return None

def _pydantic_field(field: FieldSchema, required: bool = True) -> tuple[type, Any]:
    """Return a (annotation, Field) tuple for pydantic.create_model."""
    py_type = _PYDANTIC_TYPE_MAP[field.type]
    example = _generate_example(field)
    examples = [example] if example is not None else None

    if not required or field.nullable:
        py_type = py_type | None  # type: ignore[assignment]
        default = field.default if field.default is not None else None
        return (py_type, Field(default=default, description=field.description, examples=examples))

    if field.default is not None and field.default != "uuid4":
        return (py_type, Field(default=field.default, description=field.description, examples=examples))

    return (py_type, Field(default=..., description=field.description, examples=examples))


class DTOSet(BaseModel):
    """Container for the three generated DTOs of one blueprint."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    CreateDTO: type[BaseModel]
    UpdateDTO: type[BaseModel]
    ResponseDTO: type[BaseModel]


def create_dtos(schema: ModelSchema) -> DTOSet:
    create_fields: dict[str, Any] = {}
    update_fields: dict[str, Any] = {}
    response_fields: dict[str, Any] = {}

    for field in schema.fields:
        py_type = _PYDANTIC_TYPE_MAP[field.type]

        example = _generate_example(field)
        examples = [example] if example is not None else None

        # --- Response: all fields, ORM-aware ---
        if field.nullable:
            response_fields[field.name] = (py_type | None, Field(default=None, description=field.description, examples=examples))
        else:
            response_fields[field.name] = (py_type, Field(default=..., description=field.description, examples=examples))

        # Skip auto-generated/primary-key fields in Create & Update
        if field.primary_key:
            continue
        if field.default in ("uuid4", "now"):
            continue

        # --- Create ---
        create_fields[field.name] = _pydantic_field(field, required=not field.nullable)

        # --- Update: everything is Optional ---
        update_fields[field.name] = (py_type | None, Field(default=None, description=field.description, examples=examples))

    CreateDTO = create_model(f"{schema.model_name}Create", **create_fields)
    UpdateDTO = create_model(f"{schema.model_name}Update", **update_fields)
    ResponseDTO = create_model(
        f"{schema.model_name}Response",
        __config__=ConfigDict(from_attributes=True),
        **response_fields,
    )

    return DTOSet(CreateDTO=CreateDTO, UpdateDTO=UpdateDTO, ResponseDTO=ResponseDTO)


def build_all_dtos(schemas: list[ModelSchema]) -> dict[str, DTOSet]:
    return {schema.model_name: create_dtos(schema) for schema in schemas}
