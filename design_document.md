# CoreNexus Design Document

---
document_type: DesignDocument
version: 1.0.0
status: draft
author_agents: [PM, SA, CodeReviewer, Orchestrator]
date: 2026-05-08
project: CoreNexus
sprint: 1
---

---

## 1. Executive Summary

CoreNexus is a **Meta-System Code Generation Engine** that implements a Single Source of Truth (SSOT) architecture for REST API services. Rather than hand-writing boilerplate, engineers define data models as YAML blueprints; the system then auto-generates the full stack at startup — SQLAlchemy ORM models, Pydantic V2 DTOs, FastAPI CRUD routers, and Alembic migration scripts.

**Current State (as of 2026-05-08)**

All five implementation phases are functionally complete and confirmed through source inspection:
- Phase 1–4 code exists and is non-trivial
- 24 example YAML blueprints exist under `blueprints/`
- Dockerfile and docker-compose.yml are present
- `requirements.txt` pins all production and dev dependencies

The codebase is production-*shaped* but not production-*hardened*. Three distinct risk categories exist: a critical secret-management gap, several high-priority correctness issues that will surface under real usage, and a cluster of medium/low issues that affect long-term maintainability and operational readiness.

---

## 2. System Architecture (SA Perspective)

### 2.1 Data Flow

```
blueprints/*.yaml
    │
    ▼
SchemaParser.load_all()                      [parser.py]
    │  yaml.safe_load → ModelSchema.model_validate()
    │  Fail-Fast: SystemExit on parse or validation error
    ▼
build_all_orm_models(schemas, Base)          [orm_factory.py]
    │  type() metaclass → SQLAlchemy DeclarativeBase subclass
    │  _build_sa_column(): FieldType → mapped_column()
    │  relationship() for RelationSchema entries
    ▼
Base.metadata.create_all(conn)              [main.py lifespan]
    │  Idempotent table creation (Alembic handles real migrations)
    ▼
build_all_dtos(schemas)                      [dto_factory.py]
    │  pydantic.create_model → {Create, Update, Response}DTO
    │  Response DTO: from_attributes=True for ORM serialization
    ▼
create_crud_router(schema, orm, crud, dtos) [router_builder.py]
    │  APIRouter with prefix=/{table_name}
    │  POST / GET / GET/{id} / PUT/{id} / DELETE/{id}
    │  auth_required → Depends(verify_token) injected
    ▼
app.include_router(router, prefix="/api/v1") [main.py]
    │
    ▼
FastAPI app serving on /api/v1/{table_name}/...
```

### 2.2 Component Diagram

```mermaid
flowchart TD
    subgraph Startup["Lifespan Startup (main.py)"]
        SP[SchemaParser] -->|ModelSchema list| ORM[orm_factory]
        SP --> DTO[dto_factory]
        ORM -->|ORM classes| RB[router_builder]
        DTO -->|DTO classes| RB
        ORM -->|Base.metadata| DB[(PostgreSQL 15)]
        RB -->|APIRouter| APP[FastAPI app]
    end

    subgraph Request["Request Path"]
        CLIENT[HTTP Client] --> APP
        APP -->|Depends(get_db)| SESS[AsyncSession]
        APP -->|auth_required=true| AUTH[auth.py — JWT verify]
        APP --> REPO[CRUDBase — repository.py]
        REPO --> SESS
        SESS --> DB
    end

    subgraph CLI["Migration CLI (cli.py)"]
        TYPER[Typer CLI] --> ALEMBIC[alembic revision --autogenerate]
        ALEMBIC --> SAFE[Safe-Mode scanner]
        SAFE -->|no destructive ops| APPLY[alembic upgrade head]
        SAFE -->|drop_table/drop_column| BLOCK[SystemExit 1]
    end

    subgraph QFilter["Query Filter (query_builder.py)"]
        QP["?age__gte=18&name__icontains=foo"] --> PF[parse_filters]
        PF -->|SQLAlchemy expressions| REPO
    end
```

### 2.3 Key Modules

| Module | Responsibility | Notable Pattern |
|---|---|---|
| `schema_def.py` | Meta-schema (Pydantic V2) | FieldType enum with `_missing_` for clear errors |
| `orm_factory.py` | Dynamic ORM class generation | `type()` metaclass; `_class_registry` cache check |
| `dto_factory.py` | Dynamic Pydantic DTO generation | `create_model`; three-DTO pattern (Create/Update/Response) |
| `parser.py` | YAML blueprint loading | `yaml.safe_load`; Fail-Fast via `SystemExit` |
| `repository.py` | Generic async CRUD | Generic `CRUDBase[M, C, U]`; hardcoded `.id` PK lookup |
| `router_builder.py` | Dynamic FastAPI router | `exec()` for POST/PUT type-annotated handlers |
| `query_builder.py` | Magic filter protocol | Django-style `__gte`/`__icontains` operators |
| `auth.py` | JWT issue + verify | python-jose + bcrypt; hardcoded `SECRET_KEY` |
| `database.py` | Async engine + session | `create_async_engine` with pool tuning |
| `main.py` | App + lifespan + auth endpoints | `_RegDTO` inline model; `app.state` for ORM |
| `cli.py` | Migration CLI | Typer; regex-based Safe-Mode scan |
| `alembic/env.py` | Dynamic metadata for migrations | Imports ORM factories at module load time |

---

## 3. Current Implementation Status

### 3.1 What Is Complete

| Component | Status | Notes |
|---|---|---|
| Meta-schema (`schema_def.py`) | Complete | `FieldType`, `RelationType`, `FieldSchema`, `RelationSchema`, `ModelSchema` |
| ORM factory | Complete | All 8 field types mapped; FK + relationship support |
| DTO factory | Complete | 3-DTO pattern with OpenAPI `examples`; `from_attributes` on Response |
| YAML parser | Complete | Fail-Fast on missing dir, missing files, parse errors, validation errors, duplicates |
| Generic repository | Complete | `get`, `get_multi` (with filters/ordering), `create`, `update`, `remove` |
| Router builder | Complete | Full CRUD; `PaginatedResponse`; `auth_required` support |
| Magic filter protocol | Complete | 12 operators including `icontains`, `in`, `isnull` |
| JWT auth | Functional | Issue + verify + bcrypt; missing env-var injection |
| Alembic integration | Complete | Dynamic metadata in `env.py`; async engine for online migrations |
| Migration CLI | Complete | Typer; `makemigrations`, `migrate`, `downgrade`, `status`; Safe-Mode |
| Docker | Complete | `Dockerfile` + `docker-compose.yml` exist |
| Example blueprints | Complete | 24 YAML blueprints covering diverse domains |
| Unit tests (Phase 1) | Present | `tests/test_phase1.py` uses YAML fixtures |
| Integration tests (Phase 2–5) | Present | Files exist; content depth not fully inspected |

### 3.2 What Is Missing or Incomplete

| Gap | Severity | Details |
|---|---|---|
| `SECRET_KEY` from environment | Critical | Hardcoded in `auth.py:18` |
| PATCH endpoint | High | Only PUT exists; partial updates require full payload |
| `datetime.utcnow()` usage | High | Deprecated in Python 3.12+; two call sites in `auth.py` |
| CORS configuration | Medium | No `CORSMiddleware` in `main.py` |
| Rate limiting | Low | No middleware or decorator present |
| Refresh token | Low | Access-only token issuance; no rotation |
| Error response format | Medium | `IntegrityError` handler uses non-standard shape |

---

## 4. Identified Issues & Improvement Areas

### 4.1 Critical (Security)

#### CRIT-1 — Hardcoded JWT Secret Key
**Location:** `src/core/auth.py:18`
```python
SECRET_KEY = "super-secret-meta-system-key"
```
**Risk:** Anyone with access to the repository (including git history) can forge valid JWT tokens for any user. This completely bypasses authentication.
**Fix:** Load from `os.getenv("SECRET_KEY")` and raise `ValueError` at startup if unset. Minimum 32 bytes of random entropy (use `secrets.token_hex(32)`).

#### CRIT-2 — `exec()` for Route Handler Registration
**Location:** `src/core/router_builder.py:43-56` (POST handler) and `110-128` (PUT handler)
```python
exec(
    f"""
async def _create(item: __CreateDTO, db: AsyncSession = Depends(__get_db)):
    return await __crud.create(db=db, obj_in=item)
""",
    {"__CreateDTO": CreateDTO, ...},
    _ns := {},
)
```
**Risk:** No user-controlled input reaches the `exec()` call today (only `CreateDTO` class references are injected). However, the pattern is difficult to audit, breaks debugger step-through, produces anonymous stack frames in tracebacks, and creates a maintenance hazard if someone later passes user-influenced data into the f-string template. The root problem it solves (FastAPI needs the type annotation at function definition time) has a clean solution via closure factories.
**Fix:** Replace with a closure factory function (see Section 6).

---

### 4.2 High (Correctness / API Design)

#### HIGH-1 — Hardcoded `.id` Primary Key in Repository
**Location:** `src/core/repository.py:28`
```python
result = await db.execute(select(self.model).where(self.model.id == id_val))
```
**Risk:** Any blueprint that names its PK something other than `id` (e.g., `user_id`, `pk`, `code`) will produce an `AttributeError` at runtime. The `ModelSchema` validator only requires that *some* field has `primary_key: True`, not that it is named `id`.
**Fix:** Inspect `self.model.__table__.primary_key` to find the actual PK column(s) at `CRUDBase.__init__` time and store the column reference. See ADR-004.

#### HIGH-2 — No PATCH Endpoint
**Location:** `src/core/router_builder.py` — absence
**Risk:** Clients performing partial updates (e.g., updating only a user's email) must send the entire resource representation on a PUT. This breaks REST semantics and creates bandwidth waste; more critically, nullable fields not sent by the client get overwritten with `None` because `UpdateDTO` makes all fields `Optional` with `default=None`.
**Fix:** Add a `PATCH /{id}` route using the same `UpdateDTO` (already all-optional) and call `crud.update()` which already uses `exclude_unset=True`.

#### HIGH-3 — `datetime.utcnow()` Deprecated
**Location:** `src/core/auth.py:27,30`
```python
expire = datetime.utcnow() + expires_delta
expire = datetime.utcnow() + timedelta(minutes=15)
```
**Risk:** Python 3.12 emits `DeprecationWarning` on every token issuance. Python 3.14 will remove `utcnow()`. Aware datetimes also prevent subtle DST-related token expiry bugs.
**Fix:** Replace with `datetime.now(timezone.utc)`. Requires `from datetime import timezone`.

#### HIGH-4 — Blueprint Format Mismatch (Docs vs. Code)
**Locations:** `CLAUDE.md` ("JSON Schema Blueprints"), `README.md` ("JSON Blueprints"), vs. `parser.py:22` (`glob("*.yaml")`), `parser.py:41` (`yaml.safe_load`)
**Risk:** New contributors following the documentation will create `.json` files that are silently ignored by the parser, then spend time debugging a non-obvious `SystemExit: No YAML blueprint files found` error.
**Fix:** Per ADR-002, keep YAML (it is more human-readable and already the entire `blueprints/` directory uses `.yaml`). Update `CLAUDE.md` and `README.md` to say "YAML blueprints".

---

### 4.3 Medium (Architecture / Maintainability)

#### MED-1 — Non-Standard Error Response Shape
**Location:** `src/main.py:80-83`
```python
content={"error": "Resource Conflict", "detail": "A unique constraint..."}
```
**Risk:** The project's own constitution (`CLAUDE.md` Section 12) mandates:
```json
{"success": false, "error": {"code": "ERR_...", "message": "..."}, "meta": {...}}
```
The `404` responses from `router_builder.py` also use FastAPI's default `{"detail": "..."}` shape. Clients parsing error responses need to handle two distinct schemas.
**Fix:** Add a custom `HTTPException` handler and a standardized error factory function. Wrap all `raise HTTPException(...)` calls to emit `ERR_{DOMAIN}_{REASON}` codes.

#### MED-2 — `_RegDTO` Inline Pydantic Model
**Location:** `src/main.py:105-113`
```python
@app.post("/api/v1/auth/register", ...)
async def register(body: RegisterRequest, db=Depends(get_db)):
    class _RegDTO(BaseModel):
        email: str
        hashed_password: str
        full_name: str | None = None
    dto = _RegDTO(...)
```
**Risk:** A Pydantic model defined inside a request handler is re-created on every request (minor perf), is invisible to OpenAPI schema generation, and cannot be reused by tests or other handlers.
**Fix:** Extract `_RegDTO` to a module-level class, or — better — pass the data dict directly to `user_crud.create()` since `CRUDBase.create()` already handles plain dicts via `hasattr(obj_in, "model_dump")`.

#### MED-3 — Untyped `app.state` Access
**Location:** `src/main.py:58-60, 99, 103, 121`
```python
app.state.user_orm = orm_models["User"]
app.state.user_crud = CRUDBase(orm_models["User"])
...
user_crud = getattr(app.state, "user_crud", None)
```
**Risk:** Typo-prone; no IDE autocomplete; silent `None` if the `User` blueprint does not exist. The `503` response is correct behavior, but the check pattern is repeated and fragile.
**Fix:** Use a typed `AppState` Pydantic model or typed `dataclass` and assign it to `app.state` in lifespan. Alternatively, use `request.app.state` with explicit Optional typing via a `TypedDict`.

#### MED-4 — `Base.registry._class_registry` Private API Access
**Location:** `src/core/orm_factory.py:72`
```python
existing = Base.registry._class_registry.get(schema.model_name)
```
**Risk:** `_class_registry` is a private, undocumented attribute on SQLAlchemy's `RegistryManager`. It has changed between minor versions (it was `_class_registry` in 2.0, but the access path may shift). A SQLAlchemy minor upgrade could silently return `None` and cause duplicate table definition errors.
**Fix:** Catch `sqlalchemy.exc.InvalidRequestError` (raised when attempting to redefine a mapped class) or maintain an explicit `dict[str, type]` cache at the factory level.

---

### 4.4 Low (Production Readiness)

#### LOW-1 — No CORS Configuration
**Location:** `src/main.py` — absence
**Risk:** Cross-origin requests will be blocked by browsers by default (no `Access-Control-Allow-Origin` header). For any browser-based frontend, this is a total blocker.
**Fix:** Add `CORSMiddleware` with an explicit allowlist from environment variable. Default to `["http://localhost:3000"]` in development.

#### LOW-2 — No Rate Limiting
**Risk:** Public endpoints (`/api/v1/auth/token`, `/api/v1/auth/register`) are open to credential stuffing and brute force. `CLAUDE.md` Section 11 mandates 100 req/min/IP.
**Fix:** Add `slowapi` (built on `limits`) or a reverse-proxy-level rule (nginx `limit_req`). Document the chosen approach.

#### LOW-3 — No Refresh Token
**Location:** `src/core/auth.py`, `src/main.py` — absence
**Risk:** Access tokens expire after 30 minutes and users must re-authenticate. `CLAUDE.md` Section 11 requires Refresh Token Rotation.
**Fix:** Add a `POST /api/v1/auth/refresh` endpoint. Store refresh tokens in a dedicated table (or Redis) with single-use enforcement.

#### LOW-4 — No `requirements-dev.txt` Separation
**Location:** `requirements.txt:15-19`
**Risk:** `pytest`, `httpx`, and `python-multipart` are bundled with production dependencies. Docker builds for production install test tooling unnecessarily.
**Fix:** Split into `requirements.txt` (prod) and `requirements-dev.txt` (test/lint). Update Dockerfile to use only prod deps.

---

## 5. Architectural Decisions Required

The following ADRs have been created under `.claude/.decisions/`:

| ADR | Topic | Status |
|---|---|---|
| ADR-001 | Secret management — env var vs. hardcoded | Accepted |
| ADR-002 | Blueprint format — YAML vs. JSON | Accepted |
| ADR-003 | Dynamic routing — `exec()` vs. closure factory | Accepted |
| ADR-004 | Primary key abstraction — hardcoded `.id` vs. generic PK lookup | Accepted |

---

## 6. Proposed Improvements (Concrete Recommendations)

### 6.1 Fix CRIT-1: Secret Key from Environment

```python
# src/core/auth.py
import os

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "SECRET_KEY environment variable is not set. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
```

Add `SECRET_KEY=<value>` to `.env` (already in `.gitignore` via `python-dotenv`). Use `pydantic-settings` `BaseSettings` for a typed config object.

### 6.2 Fix CRIT-2: Replace `exec()` with Closure Factory

```python
# router_builder.py — closure factory pattern
def _make_create_handler(CreateDTO, get_db, crud):
    async def _create(
        item: CreateDTO,
        db: AsyncSession = Depends(get_db),
    ):
        return await crud.create(db=db, obj_in=item)
    # Patch the annotation so FastAPI sees the concrete type
    _create.__annotations__["item"] = CreateDTO
    return _create
```

This gives FastAPI the correct type annotation at registration time without `exec()`, preserves debuggability, and survives static analysis.

### 6.3 Fix HIGH-1: Generic PK Lookup

```python
# src/core/repository.py
class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]) -> None:
        self.model = model
        # Resolve PK column at construction time
        pk_cols = list(model.__table__.primary_key.columns)
        if len(pk_cols) != 1:
            raise ValueError(f"{model.__name__} must have exactly one PK column")
        self._pk_col = pk_cols[0]
        self._pk_attr = getattr(model, self._pk_col.name)

    async def get(self, db: AsyncSession, id: Any) -> ModelType | None:
        result = await db.execute(
            select(self.model).where(self._pk_attr == id)
        )
        return result.scalar_one_or_none()
```

### 6.4 Fix HIGH-2: Add PATCH Endpoint

In `router_builder.py`, after the PUT route registration, add:

```python
exec(
    # OR use closure factory pattern from 6.2
    ...
)
router.add_api_route(
    "/{id}",
    _ns_patch["_patch"],
    methods=["PATCH"],
    response_model=ResponseDTO,
    dependencies=dependencies,
    summary=f"Partially update a {schema.model_name}",
)
```

`CRUDBase.update()` already uses `exclude_unset=True`, making it correct for PATCH semantics.

### 6.5 Fix HIGH-3: Timezone-Aware Datetimes

```python
# src/core/auth.py
from datetime import datetime, timedelta, timezone

# Replace both occurrences:
expire = datetime.now(timezone.utc) + expires_delta
expire = datetime.now(timezone.utc) + timedelta(minutes=15)
```

### 6.6 Fix MED-1: Standardized Error Response

```python
# src/core/errors.py  (new module)
from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import uuid

def error_response(status_code: int, code: str, message: str, detail: str | None = None):
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {"code": code, "message": message, "detail": detail},
            "meta": {
                "request_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "api_version": "0.1.0",
            },
        },
    )
```

Register a global `HTTPException` handler in `main.py` that converts `detail` strings to this format.

### 6.7 Fix MED-4: Private API Cache Replacement

```python
# src/core/factory/orm_factory.py
_MODEL_CACHE: dict[str, type] = {}

def create_orm_model(schema: ModelSchema, Base: type[DeclarativeBase]) -> type:
    if schema.model_name in _MODEL_CACHE:
        return _MODEL_CACHE[schema.model_name]
    ...
    model_cls = type(schema.model_name, (Base,), attrs)
    _MODEL_CACHE[schema.model_name] = model_cls
    return model_cls
```

---

## 7. Sprint Plan Summary

**Sprint 1 (2026-05-08 onward)** targets all CRITICAL and HIGH issues:

| Priority | Task | File | Issue |
|---|---|---|---|
| P0 | Load SECRET_KEY from env | `auth.py` | CRIT-1 |
| P0 | Replace `exec()` with closure factory | `router_builder.py` | CRIT-2 |
| P1 | Generic PK resolution in CRUDBase | `repository.py` | HIGH-1 |
| P1 | Add PATCH endpoint | `router_builder.py` | HIGH-2 |
| P1 | Fix `datetime.utcnow()` | `auth.py` | HIGH-3 |
| P1 | Update docs to say YAML (not JSON) | `CLAUDE.md`, `README.md` | HIGH-4 |

**Sprint 2** targets MEDIUM issues:
- Standardized error response format (MED-1)
- Extract `_RegDTO` and unify auth endpoint style (MED-2)
- Typed `app.state` via `pydantic-settings` (MED-3)
- Replace `_class_registry` access with explicit cache (MED-4)

**Sprint 3** targets LOW issues:
- CORS middleware with env-var allowlist (LOW-1)
- Rate limiting via `slowapi` (LOW-2)
- Refresh token with rotation (LOW-3)
- Split `requirements.txt` / `requirements-dev.txt` (LOW-4)

See `.claude/sprint/current/plan.md` for the full Sprint 1 task table with acceptance criteria.
