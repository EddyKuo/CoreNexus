from __future__ import annotations

from typing import Any, Generic, Type, TypeVar
from uuid import UUID

from sqlalchemy import select, func, inspect as sa_inspect
from sqlalchemy import Uuid as SAUuid
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from sqlalchemy.dialects.postgresql import UUID as PGUUID
    _UUID_TYPES = (SAUuid, PGUUID)
except ImportError:
    _UUID_TYPES = (SAUuid,)  # type: ignore[assignment]

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]) -> None:
        self.model = model
        mapper = sa_inspect(model)
        pk_cols = list(mapper.mapper.primary_key)
        if len(pk_cols) != 1:
            raise ValueError(
                f"CRUDBase requires a single-column primary key; "
                f"{model.__name__} has {len(pk_cols)}: {[c.name for c in pk_cols]}"
            )
        self._pk_col = pk_cols[0]
        self._pk_attr = getattr(model, self._pk_col.name)
        self._pk_is_uuid = isinstance(self._pk_col.type, _UUID_TYPES)

    async def get(self, db: AsyncSession, id: Any) -> ModelType | None:
        id_val = id
        if self._pk_is_uuid and isinstance(id, str):
            try:
                id_val = UUID(id)
            except ValueError:
                return None
        result = await db.execute(select(self.model).where(self._pk_attr == id_val))
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100,
        filters: list[Any] | None = None,
        order_by: list[Any] | None = None,
    ) -> tuple[list[ModelType], int]:
        query = select(self.model)
        count_query = select(func.count()).select_from(self.model)

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        if order_by:
            query = query.order_by(*order_by)

        total = (await db.execute(count_query)).scalar_one()
        rows = (await db.execute(query.offset(skip).limit(limit))).scalars().all()
        return list(rows), total

    async def create(self, db: AsyncSession, *, obj_in: CreateSchemaType) -> ModelType:
        data = obj_in.model_dump() if hasattr(obj_in, "model_dump") else dict(obj_in)
        db_obj = self.model(**data)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self, db: AsyncSession, *, db_obj: ModelType, obj_in: UpdateSchemaType
    ) -> ModelType:
        data = obj_in.model_dump(exclude_unset=True) if hasattr(obj_in, "model_dump") else dict(obj_in)
        for key, value in data.items():
            setattr(db_obj, key, value)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def remove(self, db: AsyncSession, *, id: Any) -> ModelType | None:
        db_obj = await self.get(db, id)
        if db_obj is None:
            return None
        await db.delete(db_obj)
        await db.commit()
        return db_obj
