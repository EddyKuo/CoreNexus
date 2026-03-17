"""Phase 1 unit tests — no database required."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from sqlalchemy.orm import DeclarativeBase

from src.core.factory.dto_factory import build_all_dtos, create_dtos
from src.core.factory.orm_factory import build_all_orm_models, create_orm_model
from src.core.models.schema_def import FieldSchema, FieldType, ModelSchema
from src.core.parser import SchemaParser


# ── Fixtures ─────────────────────────────────────────────────

MINIMAL_BLUEPRINT = {
    "model_name": "Article",
    "table_name": "articles",
    "fields": [
        {"name": "id", "type": "uuid", "primary_key": True, "nullable": False},
        {"name": "title", "type": "string", "length": 200, "nullable": False},
        {"name": "views", "type": "integer", "nullable": False, "default": 0},
        {"name": "active", "type": "boolean", "nullable": False, "default": True},
    ],
}


@pytest.fixture
def article_schema() -> ModelSchema:
    return ModelSchema.model_validate(MINIMAL_BLUEPRINT)


@pytest.fixture
def fresh_base():
    class TestBase(DeclarativeBase):
        pass
    return TestBase


# ── Schema Def Tests ──────────────────────────────────────────

class TestModelSchema:
    def test_valid_blueprint_parses(self, article_schema):
        assert article_schema.model_name == "Article"
        assert len(article_schema.fields) == 4

    def test_missing_primary_key_raises(self):
        bad = {**MINIMAL_BLUEPRINT, "fields": [{"name": "title", "type": "string", "nullable": True}]}
        with pytest.raises(ValidationError, match="primary_key"):
            ModelSchema.model_validate(bad)

    def test_unknown_field_type_raises(self):
        bad_field = {"name": "col", "type": "unsupported_type", "nullable": True, "primary_key": False}
        with pytest.raises(ValidationError):
            FieldSchema.model_validate(bad_field)

    def test_length_only_on_string(self):
        bad = {"name": "col", "type": "integer", "length": 100, "nullable": True, "primary_key": False}
        with pytest.raises(ValidationError, match="length"):
            FieldSchema.model_validate(bad)

    def test_model_name_must_be_pascal_case(self):
        bad = {**MINIMAL_BLUEPRINT, "model_name": "bad_name"}
        with pytest.raises(ValidationError):
            ModelSchema.model_validate(bad)

    def test_table_name_must_be_snake_case(self):
        bad = {**MINIMAL_BLUEPRINT, "table_name": "BadTable"}
        with pytest.raises(ValidationError):
            ModelSchema.model_validate(bad)


# ── ORM Factory Tests ─────────────────────────────────────────

class TestORMFactory:
    def test_creates_orm_class(self, article_schema, fresh_base):
        model = create_orm_model(article_schema, fresh_base)
        assert model.__name__ == "Article"
        assert model.__tablename__ == "articles"

    def test_orm_class_has_all_columns(self, article_schema, fresh_base):
        model = create_orm_model(article_schema, fresh_base)
        col_names = {c.key for c in model.__table__.columns}
        assert {"id", "title", "views", "active"}.issubset(col_names)

    def test_build_all_returns_dict(self, fresh_base):
        schemas = [ModelSchema.model_validate(MINIMAL_BLUEPRINT)]
        mapping = build_all_orm_models(schemas, fresh_base)
        assert "Article" in mapping


# ── DTO Factory Tests ─────────────────────────────────────────

class TestDTOFactory:
    def test_creates_three_dtos(self, article_schema):
        dto_set = create_dtos(article_schema)
        assert dto_set.CreateDTO is not None
        assert dto_set.UpdateDTO is not None
        assert dto_set.ResponseDTO is not None

    def test_create_dto_excludes_primary_key(self, article_schema):
        dto_set = create_dtos(article_schema)
        assert "id" not in dto_set.CreateDTO.model_fields

    def test_update_dto_all_fields_optional(self, article_schema):
        dto_set = create_dtos(article_schema)
        # All fields in UpdateDTO should have defaults (i.e. be optional)
        for name, field in dto_set.UpdateDTO.model_fields.items():
            assert field.is_required() is False, f"Field '{name}' should be optional in UpdateDTO"

    def test_response_dto_includes_id(self, article_schema):
        dto_set = create_dtos(article_schema)
        assert "id" in dto_set.ResponseDTO.model_fields

    def test_response_dto_from_attributes(self, article_schema):
        dto_set = create_dtos(article_schema)
        cfg = dto_set.ResponseDTO.model_config
        assert cfg.get("from_attributes") is True

    def test_build_all_dtos(self):
        schemas = [ModelSchema.model_validate(MINIMAL_BLUEPRINT)]
        result = build_all_dtos(schemas)
        assert "Article" in result


# ── Parser Tests ──────────────────────────────────────────────

class TestSchemaParser:
    def test_loads_valid_blueprints(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            valid_path = Path(tmpdir) / "valid.yaml"
            valid_path.write_text(yaml.dump(MINIMAL_BLUEPRINT, default_flow_style=False, sort_keys=False), encoding="utf-8")
            parser = SchemaParser(tmpdir)
            schemas = parser.load_all()
        assert len(schemas) == 1
        assert schemas[0].model_name == "Article"

    def test_empty_directory_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            parser = SchemaParser(tmpdir)
            with pytest.raises(SystemExit):
                parser.load_all()

    def test_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_path = Path(tmpdir) / "invalid.yaml"
            invalid_path.write_text("not a valid yaml: [", encoding="utf-8")
            parser = SchemaParser(tmpdir)
            with pytest.raises(SystemExit):
                parser.load_all()

    def test_duplicate_model_names_raise(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(2):
                (Path(tmpdir) / f"bp{i}.yaml").write_text(
                    yaml.dump(MINIMAL_BLUEPRINT, default_flow_style=False, sort_keys=False), encoding="utf-8"
                )
            parser = SchemaParser(tmpdir)
            with pytest.raises(SystemExit, match="Duplicate"):
                parser.load_all()

    def test_missing_directory_raises(self):
        parser = SchemaParser("/nonexistent/path")
        with pytest.raises(SystemExit):
            parser.load_all()
