from __future__ import annotations

from typing import Any, Type

from sqlalchemy import Boolean, Float, Integer, asc, desc

_RESERVED_PARAMS = {"skip", "limit", "sort"}


def _coerce(column: Any, value: Any) -> Any:
    """Coerce a string query-param value to the column's Python type."""
    try:
        col_type = column.property.columns[0].type
        if isinstance(col_type, Integer):
            return int(value)
        if isinstance(col_type, Float):
            return float(value)
        if isinstance(col_type, Boolean):
            return str(value).lower() in ("true", "1", "yes")
    except Exception:
        pass
    return value


_OPERATOR_MAP = {
    "eq":         lambda col, val: col == _coerce(col, val),
    "ne":         lambda col, val: col != _coerce(col, val),
    "gt":         lambda col, val: col > _coerce(col, val),
    "gte":        lambda col, val: col >= _coerce(col, val),
    "lt":         lambda col, val: col < _coerce(col, val),
    "lte":        lambda col, val: col <= _coerce(col, val),
    "icontains":  lambda col, val: col.ilike(f"%{val}%"),
    "contains":   lambda col, val: col.like(f"%{val}%"),
    "startswith": lambda col, val: col.ilike(f"{val}%"),
    "endswith":   lambda col, val: col.ilike(f"%{val}"),
    "in":         lambda col, val: col.in_(val.split(",") if isinstance(val, str) else val),
    "isnull":     lambda col, val: col.is_(None) if val in ("true", "1", True) else col.isnot(None),
}


def parse_filters(model: Type, query_params: dict[str, Any]) -> list[Any]:
    """Convert URL query params to SQLAlchemy filter expressions.

    Supports Django-style double-underscore operators:
        ?age__gte=18&name__icontains=admin&status=active
    """
    filters = []
    for key, value in query_params.items():
        if key in _RESERVED_PARAMS:
            continue

        if "__" in key:
            field_name, operator = key.split("__", 1)
        else:
            field_name, operator = key, "eq"

        column = getattr(model, field_name, None)
        if column is None:
            continue

        handler = _OPERATOR_MAP.get(operator)
        if handler is None:
            continue

        filters.append(handler(column, value))

    return filters


def parse_ordering(model: Type, sort_param: str | None) -> list[Any]:
    """Parse comma-separated sort string into SQLAlchemy order_by clauses.

    e.g. sort=-created_at,name  →  [desc(created_at), asc(name)]
    """
    if not sort_param:
        return []

    clauses = []
    for part in sort_param.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("-"):
            field_name = part[1:]
            direction = desc
        else:
            field_name = part
            direction = asc

        column = getattr(model, field_name, None)
        if column is not None:
            clauses.append(direction(column))

    return clauses
