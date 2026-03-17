from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends

from src.core.auth import create_access_token, hash_password, verify_password, timedelta, ACCESS_TOKEN_EXPIRE_MINUTES

from src.core.factory.dto_factory import build_all_dtos
from src.core.factory.orm_factory import build_all_orm_models
from src.core.parser import SchemaParser
from src.core.repository import CRUDBase
from src.core.router_builder import create_crud_router
from src.database import Base, engine, get_db
from sqlalchemy import select


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────
    # 1. Parse & validate all blueprints (Fail-Fast)
    parser = SchemaParser("blueprints")
    schemas = parser.load_all()

    # 2. Generate ORM models → populates Base.metadata
    orm_models = build_all_orm_models(schemas, Base)

    # 3. Create tables (idempotent; Alembic handles real migrations)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 4. Generate DTOs
    dto_sets = build_all_dtos(schemas)

    # 5. Build and mount routers
    schema_map = {s.model_name: s for s in schemas}
    for model_name, orm_model in orm_models.items():
        model_schema = schema_map[model_name]
        dtos = dto_sets[model_name]
        crud = CRUDBase(orm_model)
        router = create_crud_router(
            schema=model_schema,
            orm_model=orm_model,
            crud=crud,
            CreateDTO=dtos.CreateDTO,
            UpdateDTO=dtos.UpdateDTO,
            ResponseDTO=dtos.ResponseDTO,
            get_db=get_db,
        )
        app.include_router(router, prefix="/api/v1")

    # Store User CRUD for the register endpoint
    if "User" in orm_models:
        app.state.user_orm = orm_models["User"]
        app.state.user_crud = CRUDBase(orm_models["User"])

    print(f"✓ CoreNexus started — {len(schemas)} blueprint(s) loaded")
    yield

    # ── Shutdown ──────────────────────────────────────────────
    await engine.dispose()


app = FastAPI(
    title="CoreNexus",
    description="Meta-System Code Generation Engine — SSOT-driven REST API",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Global Exception Handlers ────────────────────────────────
@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": "Resource Conflict", "detail": "A unique constraint or foreign key was violated."},
    )


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None


@app.post("/api/v1/auth/register", tags=["auth"], status_code=201)
async def register(body: RegisterRequest, db=Depends(get_db)):
    """Create a new user account. Password is hashed automatically."""
    user_crud = getattr(app.state, "user_crud", None)
    if user_crud is None:
        raise HTTPException(status_code=503, detail="User model not available")

    UserOrm = app.state.user_orm

    class _RegDTO(BaseModel):
        email: str
        hashed_password: str
        full_name: str | None = None

    dto = _RegDTO(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    user = await user_crud.create(db=db, obj_in=dto)
    return {"id": str(user.id), "email": user.email, "full_name": user.full_name}


@app.post("/api/v1/auth/token", tags=["auth"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    user_orm = getattr(app.state, "user_orm", None)
    if user_orm is None:
        raise HTTPException(status_code=503, detail="User model not available")

    result = await db.execute(select(user_orm).where(user_orm.email == form_data.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
