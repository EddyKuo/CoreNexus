from __future__ import annotations

import math
from typing import Any, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import verify_token
from src.core.models.schema_def import ModelSchema
from src.core.repository import CRUDBase
from src.core.utils.query_builder import parse_filters, parse_ordering


class PaginatedResponse(BaseModel):
    total: int
    pages: int
    current_page: int
    per_page: int
    data: list[Any]


def create_crud_router(
    schema: ModelSchema,
    orm_model: type,
    crud: CRUDBase,
    CreateDTO: type[BaseModel],
    UpdateDTO: type[BaseModel],
    ResponseDTO: type[BaseModel],
    get_db,
) -> APIRouter:
    router = APIRouter(
        prefix=f"/{schema.table_name}",
        tags=[schema.model_name],
    )

    dependencies = [Depends(verify_token)] if schema.auth_required else []

    # ── POST / ──────────────────────────────────────────────
    # Build the handler with a correctly-typed `item` parameter at definition
    # time so FastAPI can inspect it properly.
    exec(
        f"""
async def _create(item: __CreateDTO, db: AsyncSession = Depends(__get_db)):
    return await __crud.create(db=db, obj_in=item)
""",
        {
            "__CreateDTO": CreateDTO,
            "AsyncSession": AsyncSession,
            "Depends": Depends,
            "__get_db": get_db,
            "__crud": crud,
        },
        _ns := {},
    )
    router.add_api_route(
        "/",
        _ns["_create"],
        methods=["POST"],
        response_model=ResponseDTO,
        status_code=201,
        dependencies=dependencies,
        summary=f"Create a new {schema.model_name}",
    )

    # ── GET / ────────────────────────────────────────────────
    @router.get(
        "/",
        dependencies=dependencies,
        summary=f"List {schema.model_name} items",
    )
    async def list_items(
        request: Request,
        skip: int = Query(0, ge=0),
        limit: int = Query(10, ge=1, le=200),
        sort: str | None = Query(None),
        db: AsyncSession = Depends(get_db),
    ):
        params = dict(request.query_params)
        filters = parse_filters(orm_model, params)
        order_by = parse_ordering(orm_model, sort)
        items, total = await crud.get_multi(
            db=db, skip=skip, limit=limit, filters=filters, order_by=order_by
        )
        pages = math.ceil(total / limit) if limit else 1
        current_page = (skip // limit) + 1 if limit else 1
        return PaginatedResponse(
            total=total,
            pages=pages,
            current_page=current_page,
            per_page=limit,
            data=[ResponseDTO.model_validate(item) for item in items],
        )

    # ── GET /{id} ────────────────────────────────────────────
    @router.get(
        "/{id}",
        response_model=ResponseDTO,
        dependencies=dependencies,
        summary=f"Get a {schema.model_name}",
    )
    async def read_item(id: str, db: AsyncSession = Depends(get_db)):
        db_obj = await crud.get(db=db, id=id)
        if db_obj is None:
            raise HTTPException(status_code=404, detail=f"{schema.model_name} not found")
        return db_obj

    # ── PUT /{id} ────────────────────────────────────────────
    exec(
        f"""
async def _update(id: str, item: __UpdateDTO, db: AsyncSession = Depends(__get_db)):
    db_obj = await __crud.get(db=db, id=id)
    if db_obj is None:
        raise __HTTPException(status_code=404, detail=__detail)
    return await __crud.update(db=db, db_obj=db_obj, obj_in=item)
""",
        {
            "__UpdateDTO": UpdateDTO,
            "AsyncSession": AsyncSession,
            "Depends": Depends,
            "__get_db": get_db,
            "__crud": crud,
            "__HTTPException": HTTPException,
            "__detail": f"{schema.model_name} not found",
        },
        _ns2 := {},
    )
    router.add_api_route(
        "/{id}",
        _ns2["_update"],
        methods=["PUT"],
        response_model=ResponseDTO,
        dependencies=dependencies,
        summary=f"Update a {schema.model_name}",
    )

    # ── DELETE /{id} ─────────────────────────────────────────
    @router.delete(
        "/{id}",
        status_code=204,
        dependencies=dependencies,
        summary=f"Delete a {schema.model_name}",
    )
    async def delete_item(id: str, db: AsyncSession = Depends(get_db)):
        db_obj = await crud.remove(db=db, id=id)
        if db_obj is None:
            raise HTTPException(status_code=404, detail=f"{schema.model_name} not found")

    return router
