"""Sprint 1 regression tests — security & correctness hardening.

Covers:
  - SECRET_KEY fail-fast on missing env var
  - Generic PK resolution (non-'id' column names)
  - Composite PK guard in CRUDBase
  - PATCH endpoint registration
  - _make_create_handler annotation injection
  - No DeprecationWarning from datetime.utcnow()
"""
from __future__ import annotations

import warnings

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import DeclarativeBase

from src.core.factory.dto_factory import create_dtos
from src.core.factory.orm_factory import create_orm_model
from src.core.models.schema_def import ModelSchema
from src.core.repository import CRUDBase


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture()
def simple_base():
    class _Base(DeclarativeBase):
        pass
    return _Base


@pytest.fixture()
def widget_schema() -> ModelSchema:
    return ModelSchema.model_validate({
        "model_name": "Widget",
        "table_name": "widgets",
        "fields": [
            {"name": "id", "type": "uuid", "primary_key": True, "nullable": False},
            {"name": "label", "type": "string", "nullable": True},
        ],
    })


# ── S1-T1: SECRET_KEY fail-fast ────────────────────────────────

def test_secret_key_missing_raises(monkeypatch):
    """_load_secret_key() must raise ValueError when SECRET_KEY env var is absent or empty.

    We test via the exported helper function rather than reimporting the module,
    which avoids brittle sys.modules teardown that breaks C-extension imports.
    """
    from src.core.auth import _load_secret_key

    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(ValueError, match="SECRET_KEY"):
        _load_secret_key()

    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValueError, match="SECRET_KEY"):
        _load_secret_key()


# ── S1-T6: Generic PK resolution ──────────────────────────────

def test_generic_pk_non_id_column_name(simple_base):
    """CRUDBase must detect the PK even when it is not named 'id'."""
    class CodeItem(simple_base):
        __tablename__ = "code_items"
        code = Column(String(50), primary_key=True)

    crud = CRUDBase(CodeItem)
    assert crud._pk_col.name == "code"
    assert not crud._pk_is_uuid


def test_generic_pk_uuid_column(simple_base):
    """CRUDBase must detect UUID PK type and set _pk_is_uuid=True."""
    from sqlalchemy import Uuid
    class UuidItem(simple_base):
        __tablename__ = "uuid_items"
        id = Column(Uuid, primary_key=True)

    crud = CRUDBase(UuidItem)
    assert crud._pk_col.name == "id"
    assert crud._pk_is_uuid is True


# ── S1-T6: Composite PK guard ─────────────────────────────────

def test_crud_base_composite_pk_raises():
    """CRUDBase must raise ValueError for models with composite primary keys."""
    class _Base(DeclarativeBase):
        pass

    class CompModel(_Base):
        __tablename__ = "comp_items"
        key1 = Column(String(50), primary_key=True)
        key2 = Column(Integer, primary_key=True)

    with pytest.raises(ValueError, match="single-column primary key"):
        CRUDBase(CompModel)


# ── S1-T4: _make_create_handler annotation injection ──────────

def test_create_handler_annotation_is_injected(widget_schema, simple_base):
    """_make_create_handler must inject CreateDTO into __annotations__['item']."""
    from src.core.router_builder import _make_create_handler
    from src.database import get_db

    orm_model = create_orm_model(widget_schema, simple_base)
    dtos = create_dtos(widget_schema)
    crud = CRUDBase(orm_model)

    handler = _make_create_handler(dtos.CreateDTO, get_db, crud)
    assert handler.__annotations__["item"] is dtos.CreateDTO


def test_update_handler_annotation_is_injected(widget_schema, simple_base):
    """_make_update_handler must inject UpdateDTO into __annotations__['item']."""
    from src.core.router_builder import _make_update_handler
    from src.database import get_db

    orm_model = create_orm_model(widget_schema, simple_base)
    dtos = create_dtos(widget_schema)
    crud = CRUDBase(orm_model)

    handler = _make_update_handler(dtos.UpdateDTO, get_db, crud, "Widget")
    assert handler.__annotations__["item"] is dtos.UpdateDTO


# ── S1-T8: PATCH endpoint in generated router ─────────────────

def test_patch_endpoint_registered(widget_schema, simple_base):
    """create_crud_router must register a PATCH /{id} route."""
    from src.core.router_builder import create_crud_router
    from src.database import get_db

    orm_model = create_orm_model(widget_schema, simple_base)
    dtos = create_dtos(widget_schema)
    crud = CRUDBase(orm_model)

    router = create_crud_router(
        schema=widget_schema,
        orm_model=orm_model,
        crud=crud,
        CreateDTO=dtos.CreateDTO,
        UpdateDTO=dtos.UpdateDTO,
        ResponseDTO=dtos.ResponseDTO,
        get_db=get_db,
    )

    all_methods: set[str] = set()
    for route in router.routes:
        if hasattr(route, "methods"):
            all_methods.update(route.methods)

    assert "PATCH" in all_methods
    assert "PUT" in all_methods


def test_router_has_all_five_http_methods(widget_schema, simple_base):
    """Generated router must expose GET (list), GET (single), POST, PUT, PATCH, DELETE."""
    from src.core.router_builder import create_crud_router
    from src.database import get_db

    orm_model = create_orm_model(widget_schema, simple_base)
    dtos = create_dtos(widget_schema)
    crud = CRUDBase(orm_model)

    router = create_crud_router(
        schema=widget_schema, orm_model=orm_model, crud=crud,
        CreateDTO=dtos.CreateDTO, UpdateDTO=dtos.UpdateDTO,
        ResponseDTO=dtos.ResponseDTO, get_db=get_db,
    )

    all_methods: set[str] = set()
    for route in router.routes:
        if hasattr(route, "methods"):
            all_methods.update(route.methods)

    assert {"GET", "POST", "PUT", "PATCH", "DELETE"}.issubset(all_methods)


# ── S1-T9: No deprecated datetime.utcnow() ────────────────────

def test_create_access_token_no_utcnow_deprecation_warning():
    """create_access_token must not trigger a DeprecationWarning from datetime.utcnow()."""
    from src.core.auth import create_access_token

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        token = create_access_token({"sub": "test@example.com"})

    assert token  # token was produced without DeprecationWarning
