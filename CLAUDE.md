# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CoreNexus is a **Meta-System Code Generation Engine** — a SSOT (Single Source of Truth) infrastructure that reads YAML Blueprints at startup and automatically generates:
- SQLAlchemy ORM models (via Python `type()` metaclass)
- Pydantic DTOs (via `pydantic.create_model`) for Create/Update/Response
- FastAPI CRUD routes (via dynamic `APIRouter`)
- Alembic migration scripts (with Safe-Mode destructive-op detection)

**Current status**: All Phase 1–5 core features implemented. Sprint 1 security & correctness hardening in progress (see `.claude/sprint/current/plan.md`).

## Technology Stack

| Layer | Choice |
|---|---|
| Web Framework | FastAPI (ASGI, lifespan events) |
| ORM | SQLAlchemy 2.0 async (`AsyncSession`, `DeclarativeBase`) |
| Validation / DTOs | Pydantic V2 (`create_model`) |
| Migrations | Alembic (env.py modified to load dynamic metadata) |
| Database | PostgreSQL 15+ |
| Async DB Driver | asyncpg |

## Planned Directory Structure

```
src/
├── core/
│   ├── models/schema_def.py     # FieldSchema, RelationSchema, ModelSchema (Pydantic meta-schema)
│   ├── factory/
│   │   ├── orm_factory.py       # type() dynamic SQLAlchemy model generation
│   │   └── dto_factory.py       # pydantic.create_model dynamic DTO generation
│   ├── parser.py                # Load & validate blueprints/*.yaml
│   ├── repository.py            # Generic async CRUD (AsyncSession)
│   ├── router_builder.py        # Bind ORM+DTOs+Repository into APIRouter
│   └── utils/query_builder.py   # Magic filter protocol (?field__gte=val)
├── database.py                  # create_async_engine + AsyncSession factory
└── main.py                      # FastAPI app with lifespan (load blueprints → mount routes)

blueprints/                      # YAML blueprint definitions (source of truth)
alembic/                         # env.py modified to load dynamic Base.metadata
cli.py                           # Auto-migration CLI (wraps alembic commands + Safe-Mode)
```

## Architecture: Data Flow

```
blueprints/*.yaml
    → parser.py (validate with Pydantic meta-schema)
    → orm_factory.py (generate SQLAlchemy Model classes)
    → dto_factory.py (generate Create/Update/Response Pydantic models)
    → router_builder.py (generate FastAPI APIRouter with CRUD endpoints)
    → main.py lifespan (register all routers on startup)
```

## Implementation Phases (plan.md)

- **Phase 1** – Schema definitions, ORM factory, DTO factory, unit tests
- **Phase 2** – Generic repository, router builder, lifespan startup, Swagger validation
- **Phase 3** – Alembic integration, dynamic metadata env.py, migration CLI, Safe-Mode (blocks `drop_column`/`drop_table`)
- **Phase 4** – Magic filter protocol (`?age__gte=18`, `?name__icontains=foo`), pagination (`PaginationSchema`), auth extension points (`auth_required: true` → `Depends` injection)
- **Phase 5** – Connection pool tuning, global exception handlers (SQLAlchemy → HTTP), Docker/docker-compose, example blueprints

## Key Design Decisions

- **JSON abstract field types** map to SQLAlchemy columns: `string→String`, `integer→Integer`, `float→Float`, `boolean→Boolean`, `datetime→DateTime`, `uuid→UUID`, `json→JSONB`
- **Safe-Mode migration**: After `alembic revision --autogenerate`, the CLI statically analyzes the generated script and raises an error if it contains destructive ops, preventing accidental data loss
- **Auth extension point**: Blueprint fields with `auth_required: true` cause router_builder to inject a FastAPI `Depends` parameter — the actual JWT/RBAC logic is plugged in separately
- **Fail-Fast startup**: All blueprint validation happens in the lifespan event before the server accepts requests

## Commands (once implemented)

```bash
# Install dependencies
pip install fastapi sqlalchemy alembic pydantic asyncpg

# Run development server
uvicorn src.main:app --reload

# Generate + apply migration
python cli.py migrate --message "add user table"

# Run tests
pytest
```
