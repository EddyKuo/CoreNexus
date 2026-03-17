from __future__ import annotations

from typing import Any, Generic, Type, TypeVar

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]) -> None:
        self.model = model

    async def get(self, db: AsyncSession, id: Any) -> ModelType | None:
        # Some UUID columns (like in SQLite testing) strictly require UUID objects
        try:
            from uuid import UUID
            if isinstance(id, str) and len(id) == 36:
                id_val = UUID(id)
            else:
                id_val = id
        except ValueError:
            id_val = id
            
        result = await db.execute(select(self.model).where(self.model.id == id_val))
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
