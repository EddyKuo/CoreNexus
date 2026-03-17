"""Phase 4 tests — Magic filters, sorting, pagination, and auth hooks.

Integration tests use an in-memory SQLite database (no PostgreSQL required).
"""
from __future__ import annotations

import yaml
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.factory.dto_factory import build_all_dtos
from src.core.factory.orm_factory import build_all_orm_models
from src.core.models.schema_def import ModelSchema
from src.core.parser import SchemaParser
from src.core.repository import CRUDBase
from src.core.router_builder import create_crud_router
from src.core.auth import verify_token
from src.core.utils.query_builder import parse_filters, parse_ordering
from src.database import Base

# ── SQLite in-memory engine for tests ────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_Session = async_sessionmaker(autocommit=False, autoflush=False, bind=_engine)


async def _get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _Session() as session:
        yield session


# ── Blueprint: filterable / sortable fields ───────────────────
ITEM_BLUEPRINT = {
    "model_name": "Item",
    "table_name": "items",
    "fields": [
        {"name": "id", "type": "uuid", "primary_key": True, "nullable": False},
        {"name": "name", "type": "string", "length": 100, "nullable": False},
        {"name": "score", "type": "integer", "nullable": False, "default": 0},
        {"name": "active", "type": "boolean", "nullable": False, "default": True},
    ],
}

AUTH_BLUEPRINT = {
    "model_name": "Secret",
    "table_name": "secrets",
    "auth_required": True,
    "fields": [
        {"name": "id", "type": "uuid", "primary_key": True, "nullable": False},
        {"name": "value", "type": "string", "length": 100, "nullable": False},
    ],
}

# ── Shared ORM / DTO / Router fixtures ───────────────────────

@pytest_asyncio.fixture(scope="module")
async def item_app() -> AsyncGenerator[FastAPI, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "item.yaml").write_text(yaml.dump(ITEM_BLUEPRINT, default_flow_style=False, sort_keys=False), encoding="utf-8")
        schemas = SchemaParser(tmpdir).load_all()
        orm_models = build_all_orm_models(schemas, Base)
        orm_model = orm_models["Item"]

        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        dtos = build_all_dtos(schemas)["Item"]
        crud = CRUDBase(orm_model)
        app = FastAPI()
        router = create_crud_router(
            schema=schemas[0],
            orm_model=orm_model,
            crud=crud,
            CreateDTO=dtos.CreateDTO,
            UpdateDTO=dtos.UpdateDTO,
            ResponseDTO=dtos.ResponseDTO,
            get_db=_get_db,
        )
        app.include_router(router)
        yield app


@pytest_asyncio.fixture
async def client(item_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=item_app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def seed_items(item_app: FastAPI, client: AsyncClient):
    """Insert 5 known items before each test, clear after."""
    items = [
        {"name": "Alpha",   "score": 10, "active": True},
        {"name": "Bravo",   "score": 30, "active": True},
        {"name": "Charlie", "score": 20, "active": False},
        {"name": "Delta",   "score": 40, "active": True},
        {"name": "Echo",    "score": 50, "active": False},
    ]
    ids = []
    for item in items:
        r = await client.post("/items/", json=item)
        ids.append(r.json()["id"])
    yield
    for id_ in ids:
        await client.delete(f"/items/{id_}")


# ─────────────────────────────────────────────────────────────
# Unit tests: parse_filters & parse_ordering
# ─────────────────────────────────────────────────────────────

class TestQueryBuilderUnit:
    def _orm_model(self):
        """Return the Item ORM class (already registered on Base)."""
        return Base.registry._class_registry.get("Item")

    def test_parse_filters_eq(self):
        model = self._orm_model()
        filters = parse_filters(model, {"name": "Alpha"})
        assert len(filters) == 1

    def test_parse_filters_gte(self):
        model = self._orm_model()
        filters = parse_filters(model, {"score__gte": "20"})
        assert len(filters) == 1

    def test_parse_filters_icontains(self):
        model = self._orm_model()
        filters = parse_filters(model, {"name__icontains": "ra"})
        assert len(filters) == 1

    def test_parse_filters_skips_reserved_params(self):
        model = self._orm_model()
        filters = parse_filters(model, {"skip": "0", "limit": "10", "sort": "-score"})
        assert filters == []

    def test_parse_filters_skips_unknown_field(self):
        model = self._orm_model()
        filters = parse_filters(model, {"nonexistent_field": "foo"})
        assert filters == []

    def test_parse_filters_skips_unknown_operator(self):
        model = self._orm_model()
        filters = parse_filters(model, {"score__regex": "^1"})
        assert filters == []

    def test_parse_ordering_asc(self):
        model = self._orm_model()
        clauses = parse_ordering(model, "score")
        assert len(clauses) == 1

    def test_parse_ordering_desc(self):
        model = self._orm_model()
        clauses = parse_ordering(model, "-score")
        assert len(clauses) == 1

    def test_parse_ordering_multiple(self):
        model = self._orm_model()
        clauses = parse_ordering(model, "-score,name")
        assert len(clauses) == 2

    def test_parse_ordering_empty(self):
        model = self._orm_model()
        assert parse_ordering(model, None) == []
        assert parse_ordering(model, "") == []


# ─────────────────────────────────────────────────────────────
# Integration tests: filtering
# ─────────────────────────────────────────────────────────────

class TestFiltering:
    async def test_filter_by_name_eq(self, client: AsyncClient):
        r = await client.get("/items/?name=Alpha")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert data["data"][0]["name"] == "Alpha"

    async def test_filter_by_score_gte(self, client: AsyncClient):
        r = await client.get("/items/?score__gte=30")
        assert r.status_code == 200
        names = {d["name"] for d in r.json()["data"]}
        assert names == {"Bravo", "Delta", "Echo"}

    async def test_filter_by_score_lte(self, client: AsyncClient):
        r = await client.get("/items/?score__lte=20")
        assert r.status_code == 200
        names = {d["name"] for d in r.json()["data"]}
        assert names == {"Alpha", "Charlie"}

    async def test_filter_icontains(self, client: AsyncClient):
        # "r" appears in "Bravo" (B-r-avo) and "Charlie" (Cha-r-lie)
        r = await client.get("/items/?name__icontains=r")
        assert r.status_code == 200
        names = {d["name"] for d in r.json()["data"]}
        assert "Bravo" in names and "Charlie" in names

    async def test_filter_active_true(self, client: AsyncClient):
        r = await client.get("/items/?active=true")
        assert r.status_code == 200
        assert all(d["active"] for d in r.json()["data"])

    async def test_filter_active_false(self, client: AsyncClient):
        r = await client.get("/items/?active=false")
        assert r.status_code == 200
        assert all(not d["active"] for d in r.json()["data"])

    async def test_combined_filters(self, client: AsyncClient):
        """active=true AND score__gte=30 → Bravo(30) and Delta(40)"""
        r = await client.get("/items/?active=true&score__gte=30")
        assert r.status_code == 200
        names = {d["name"] for d in r.json()["data"]}
        assert names == {"Bravo", "Delta"}

    async def test_no_match_returns_empty(self, client: AsyncClient):
        r = await client.get("/items/?name=NonExistent")
        assert r.status_code == 200
        assert r.json()["total"] == 0


# ─────────────────────────────────────────────────────────────
# Integration tests: sorting
# ─────────────────────────────────────────────────────────────

class TestSorting:
    async def test_sort_score_asc(self, client: AsyncClient):
        r = await client.get("/items/?sort=score&limit=5")
        assert r.status_code == 200
        scores = [d["score"] for d in r.json()["data"]]
        assert scores == sorted(scores)

    async def test_sort_score_desc(self, client: AsyncClient):
        r = await client.get("/items/?sort=-score&limit=5")
        assert r.status_code == 200
        scores = [d["score"] for d in r.json()["data"]]
        assert scores == sorted(scores, reverse=True)

    async def test_sort_name_asc(self, client: AsyncClient):
        r = await client.get("/items/?sort=name&limit=5")
        assert r.status_code == 200
        names = [d["name"] for d in r.json()["data"]]
        assert names == sorted(names)

    async def test_sort_name_desc(self, client: AsyncClient):
        r = await client.get("/items/?sort=-name&limit=5")
        assert r.status_code == 200
        names = [d["name"] for d in r.json()["data"]]
        assert names == sorted(names, reverse=True)


# ─────────────────────────────────────────────────────────────
# Integration tests: pagination
# ─────────────────────────────────────────────────────────────

class TestPagination:
    async def test_default_pagination_envelope(self, client: AsyncClient):
        r = await client.get("/items/")
        assert r.status_code == 200
        body = r.json()
        assert "total" in body
        assert "pages" in body
        assert "current_page" in body
        assert "per_page" in body
        assert "data" in body

    async def test_total_matches_seed_count(self, client: AsyncClient):
        r = await client.get("/items/?limit=100")
        assert r.json()["total"] == 5

    async def test_limit_respected(self, client: AsyncClient):
        r = await client.get("/items/?limit=2")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) == 2
        assert body["per_page"] == 2

    async def test_pages_calculated_correctly(self, client: AsyncClient):
        r = await client.get("/items/?limit=2")
        body = r.json()
        # ceil(5 / 2) = 3 pages
        assert body["pages"] == 3

    async def test_skip_moves_page(self, client: AsyncClient):
        r1 = await client.get("/items/?sort=score&limit=2&skip=0")
        r2 = await client.get("/items/?sort=score&limit=2&skip=2")
        ids1 = {d["id"] for d in r1.json()["data"]}
        ids2 = {d["id"] for d in r2.json()["data"]}
        assert ids1.isdisjoint(ids2)

    async def test_current_page_increments_with_skip(self, client: AsyncClient):
        r = await client.get("/items/?limit=2&skip=2")
        assert r.json()["current_page"] == 2

    async def test_last_page_has_remaining_items(self, client: AsyncClient):
        r = await client.get("/items/?limit=2&skip=4")
        assert len(r.json()["data"]) == 1


# ─────────────────────────────────────────────────────────────
# Integration tests: auth_required dependency hook
# ─────────────────────────────────────────────────────────────

class TestAuthHook:
    @pytest_asyncio.fixture
    async def auth_client(self) -> AsyncGenerator[AsyncClient, None]:
        """Build a minimal app from a blueprint with auth_required: true."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "secret.yaml").write_text(yaml.dump(AUTH_BLUEPRINT, default_flow_style=False, sort_keys=False), encoding="utf-8")
            schemas = SchemaParser(tmpdir).load_all()
            orm_models = build_all_orm_models(schemas, Base)
            orm_model = orm_models["Secret"]

            async with _engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            dtos = build_all_dtos(schemas)["Secret"]
            crud = CRUDBase(orm_model)
            app = FastAPI()
            router = create_crud_router(
                schema=schemas[0],
                orm_model=orm_model,
                crud=crud,
                CreateDTO=dtos.CreateDTO,
                UpdateDTO=dtos.UpdateDTO,
                ResponseDTO=dtos.ResponseDTO,
                get_db=_get_db,
            )
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                yield ac, app

    async def test_auth_block_by_default(self, auth_client):
        """Without a valid token, the route should return 401 by default."""
        ac, _ = auth_client
        r = await ac.get("/secrets/")
        assert r.status_code == 401

    async def test_auth_dependency_can_be_overridden_to_pass(self, auth_client):
        """Overriding verify_token with a mock allows the request to pass."""
        ac, app = auth_client

        def _pass():
            return {"sub": "testuser"}

        app.dependency_overrides[verify_token] = _pass
        try:
            r = await ac.get("/secrets/")
            assert r.status_code == 200
        finally:
            app.dependency_overrides.clear()

    async def test_non_auth_routes_unaffected_by_override(self, item_app: FastAPI, client: AsyncClient):
        """Routes without auth_required are not affected when verify_token is overridden."""
        def _block():
            raise HTTPException(status_code=401, detail="Unauthorized")

        item_app.dependency_overrides[verify_token] = _block
        try:
            r = await client.get("/items/")
            # Items have no auth_required, so they should still return 200
            assert r.status_code == 200
        finally:
            item_app.dependency_overrides.clear()
