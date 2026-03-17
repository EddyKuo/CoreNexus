"""Phase 2 Integration tests — Testing dynamic FastAPI routers with an in-memory SQLite DB."""
from __future__ import annotations

import yaml
import os
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.factory.dto_factory import build_all_dtos
from src.core.factory.orm_factory import build_all_orm_models
from src.core.parser import SchemaParser
from src.core.repository import CRUDBase
from src.core.router_builder import create_crud_router
from src.database import Base, get_db

# ── Use in-memory SQLite for tests ───────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_recycle=3600,
)
TestingSessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


# ── Fixtures ─────────────────────────────────────────────────

MINIMAL_BLUEPRINT = {
    "model_name": "Task",
    "table_name": "tasks",
    "fields": [
        {"name": "id", "type": "uuid", "primary_key": True, "nullable": False},
        {"name": "title", "type": "string", "length": 100, "nullable": False},
        {"name": "done", "type": "boolean", "nullable": False, "default": False},
    ],
}


@pytest_asyncio.fixture
async def test_app() -> AsyncGenerator[FastAPI, None]:
    """Dynamically construct a FastAPI app hooked up to our Meta-System generators."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bp_path = Path(tmpdir) / "task.yaml"
        bp_path.write_text(yaml.dump(MINIMAL_BLUEPRINT, default_flow_style=False, sort_keys=False), encoding="utf-8")

        os.environ["BLUEPRINTS_DIR"] = str(tmpdir)
        parser = SchemaParser(tmpdir)
        schemas = parser.load_all()
        schema = schemas[0]

        # 2. Build ORM
        orm_models = build_all_orm_models(schemas, Base)
        orm_model = orm_models["Task"]

        # 3. Create tables in SQLite memory
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        # 4. Build DTOs
        dtos = build_all_dtos(schemas)["Task"]

        # 5. Build Router
        app = FastAPI()
        crud = CRUDBase(orm_model)
        router = create_crud_router(
            schema=schema,
            orm_model=orm_model,
            crud=crud,
            CreateDTO=dtos.CreateDTO,
            UpdateDTO=dtos.UpdateDTO,
            ResponseDTO=dtos.ResponseDTO,
            get_db=override_get_db,  # Inject test DB
        )
        app.include_router(router)

        yield app


@pytest_asyncio.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTPX AsyncClient that bypasses network to test our FastAPI app directly."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Integration Tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_dynamic_crud_endpoints(client: AsyncClient):
    # ── 1. Create a Task (POST) ──
    create_payload = {"title": "Learn Meta-Programming"}
    resp = await client.post("/tasks/", json=create_payload)
    if resp.status_code != 201:
        import json
        Path("test_err_output.txt").write_text(json.dumps(resp.json()), encoding="utf-8")
    assert resp.status_code == 201
    
    data = resp.json()
    assert data["title"] == "Learn Meta-Programming"
    assert data["done"] is False  # Testing the default value mapped by Factory
    assert "id" in data
    
    task_id = data["id"]

    # ── 2. Read the Task (GET /{id}) ──
    resp = await client.get(f"/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == task_id
    assert resp.json()["title"] == "Learn Meta-Programming"

    # ── 3. Update the Task (PUT /{id}) ──
    update_payload = {"done": True} # Testing Partial update semantics
    resp = await client.put(f"/tasks/{task_id}", json=update_payload)
    assert resp.status_code == 200
    assert resp.json()["done"] is True
    # Title should remain unmodified
    assert resp.json()["title"] == "Learn Meta-Programming"

    # ── 4. List Tasks (GET /) ──
    resp = await client.get("/tasks/")
    assert resp.status_code == 200
    list_data = resp.json()
    assert list_data["total"] == 1
    assert list_data["current_page"] == 1
    assert len(list_data["data"]) == 1
    assert list_data["data"][0]["id"] == task_id

    # ── 5. Delete the Task (DELETE /{id}) ──
    resp = await client.delete(f"/tasks/{task_id}")
    assert resp.status_code == 204

    # ── 6. Verify Deletion (GET /{id}) ──
    resp = await client.get(f"/tasks/{task_id}")
    assert resp.status_code == 404

@pytest.mark.asyncio
async def test_openapi_schema_generation(client: AsyncClient):
    """Fetch the OpenAPI JSON and print out the dynamically generated routes."""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()

    print("\n" + "="*50)
    print("🌍 DYNAMICALLY GENERATED API ENDPOINTS")
    print("="*50)
    
    paths = schema.get("paths", {})
    for path, operations in paths.items():
        for method, details in operations.items():
            summary = details.get("summary", "")
            print(f"[{method.upper():<6}] {path:<20} -> {summary}")
            
    print("="*50 + "\n")
    
    # Verify our Task endpoints actually exist in the OpenAPI spec
    assert "/tasks/" in paths
    assert "post" in paths["/tasks/"]
    assert "get" in paths["/tasks/"]
    assert "/tasks/{id}" in paths
    assert "get" in paths["/tasks/{id}"]
    assert "put" in paths["/tasks/{id}"]
    assert "delete" in paths["/tasks/{id}"]
