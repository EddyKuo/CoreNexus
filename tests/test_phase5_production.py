"""Phase 5 tests — Production hardening: exception translation, pool config, health.

Integration tests use in-memory SQLite (no PostgreSQL required).
"""
from __future__ import annotations

import yaml
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.factory.dto_factory import build_all_dtos
from src.core.factory.orm_factory import build_all_orm_models
from src.core.parser import SchemaParser
from src.core.repository import CRUDBase
from src.core.router_builder import create_crud_router
from src.database import Base, engine as prod_engine

# ── SQLite in-memory engine for tests ────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_Session = async_sessionmaker(autocommit=False, autoflush=False, bind=_engine)


async def _get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _Session() as session:
        yield session


# ── Blueprint: unique constraint for conflict testing ─────────
MEMBER_BLUEPRINT = {
    "model_name": "Member",
    "table_name": "members",
    "fields": [
        {"name": "id", "type": "uuid", "primary_key": True, "nullable": False},
        {"name": "email", "type": "string", "length": 255, "nullable": False, "unique": True},
    ],
}


def _make_app_with_handler() -> tuple[FastAPI, type]:
    """Build a FastAPI app with IntegrityError → 409 exception handler."""
    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "member.yaml").write_text(yaml.dump(MEMBER_BLUEPRINT, default_flow_style=False, sort_keys=False), encoding="utf-8")
        schemas = SchemaParser(tmpdir).load_all()
        orm_models = build_all_orm_models(schemas, Base)
        orm_model = orm_models["Member"]
        dtos = build_all_dtos(schemas)["Member"]
        crud = CRUDBase(orm_model)

        app = FastAPI()

        # ── Phase 5: Global IntegrityError handler ────────────
        @app.exception_handler(IntegrityError)
        async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
            return JSONResponse(
                status_code=409,
                content={"error": "Resource Conflict", "detail": "A unique constraint or foreign key was violated."},
            )

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
        return app, orm_model


@pytest_asyncio.fixture
async def member_client() -> AsyncGenerator[AsyncClient, None]:
    app, orm_model = _make_app_with_handler()

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ─────────────────────────────────────────────────────────────
# Phase 5.1 — Connection Pool Configuration
# ─────────────────────────────────────────────────────────────

class TestConnectionPoolConfig:
    def test_pool_size(self):
        assert prod_engine.pool.size() == 20

    def test_max_overflow(self):
        assert prod_engine.pool._max_overflow == 10

    def test_pool_recycle(self):
        assert prod_engine.pool._recycle == 3600

    def test_pool_timeout(self):
        assert prod_engine.pool._timeout == 30

    def test_pool_pre_ping_enabled(self):
        assert prod_engine.pool._pre_ping is True


# ─────────────────────────────────────────────────────────────
# Phase 5.2 — Global Exception Handling
# ─────────────────────────────────────────────────────────────

class TestExceptionHandling:
    async def test_integrity_error_returns_409(self, member_client: AsyncClient):
        """Creating two members with the same email → second returns 409."""
        payload = {"email": "alice@example.com"}
        r1 = await member_client.post("/members/", json=payload)
        assert r1.status_code == 201

        r2 = await member_client.post("/members/", json=payload)
        assert r2.status_code == 409

    async def test_409_response_body_structure(self, member_client: AsyncClient):
        """409 body must contain 'error' and 'detail' keys."""
        payload = {"email": "bob@example.com"}
        await member_client.post("/members/", json=payload)
        r = await member_client.post("/members/", json=payload)
        body = r.json()
        assert "error" in body
        assert "detail" in body

    async def test_first_create_still_succeeds(self, member_client: AsyncClient):
        """Non-conflicting creates must continue to return 201."""
        r = await member_client.post("/members/", json={"email": "charlie@example.com"})
        assert r.status_code == 201

    async def test_404_for_missing_resource(self, member_client: AsyncClient):
        """GET a non-existent ID returns 404, not 500."""
        r = await member_client.get("/members/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

    async def test_404_delete_missing_resource(self, member_client: AsyncClient):
        """DELETE a non-existent ID returns 404."""
        r = await member_client.delete("/members/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

    async def test_404_update_missing_resource(self, member_client: AsyncClient):
        """PUT a non-existent ID returns 404."""
        r = await member_client.put(
            "/members/00000000-0000-0000-0000-000000000000",
            json={"email": "x@x.com"},
        )
        assert r.status_code == 404


# ─────────────────────────────────────────────────────────────
# Phase 5.3 — Health & System Endpoints
# ─────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    @pytest_asyncio.fixture
    async def health_client(self) -> AsyncGenerator[AsyncClient, None]:
        """Minimal app with only the /health route."""
        from src.main import app as main_app
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as ac:
            yield ac

    async def test_health_returns_200(self, health_client: AsyncClient):
        r = await health_client.get("/health")
        assert r.status_code == 200

    async def test_health_response_body(self, health_client: AsyncClient):
        r = await health_client.get("/health")
        assert r.json() == {"status": "ok"}
