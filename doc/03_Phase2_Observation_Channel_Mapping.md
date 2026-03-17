# Phase 2: 觀測通道映射 (Dynamic Routing & API Integration)

本階段將把 Phase 1 生成出來的靜態結構類別 (ORM / DTO) 對接到網路層，使得所有定義好的藍圖自動產生出符合 RESTful 規範的 HTTP API。

## Task 2.1: 實作通用資料存取層 (Generic Repository Pattern)

為了保證路由層的輕量，我們不應該在路由函數中直接撰寫 SQLAlchemy 語句。必須使用泛型 (Generics) 設計一個通用的 Repository，封裝 CRUD 異步邏輯。

### 2.1.1 Generic Repository 設計規範
```python
from typing import Generic, TypeVar, Type

ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")

class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    async def get(self, db: AsyncSession, id: Any) -> ModelType | None:
        pass
        
    async def get_multi(self, db: AsyncSession, *, skip: int = 0, limit: int = 100) -> list[ModelType]:
        pass
        
    async def create(self, db: AsyncSession, *, obj_in: CreateSchemaType) -> ModelType:
        # obj_in dict -> instance -> db.add() -> db.commit() -> db.refresh()
        pass
        
    async def update(self, db: AsyncSession, *, db_obj: ModelType, obj_in: UpdateSchemaType) -> ModelType:
        pass
        
    async def remove(self, db: AsyncSession, *, id: Any) -> ModelType:
        pass
```

## Task 2.2: 實作動態路由工廠 (Router Builder)

我們需要一個工廠函數，傳入 ORM Class 及其 DTO Classes，自動產出一個封裝好所有端點的 `APIRouter`。

### 2.2.1 動態綁定 Endpoints
```python
from fastapi import APIRouter, Depends, HTTPException

def create_crud_router(
    model_name: str, 
    crud_repo: CRUDBase, 
    CreateDTO, 
    UpdateDTO, 
    ResponseDTO
) -> APIRouter:
    
    router = APIRouter(prefix=f"/{model_name.lower()}s", tags=[model_name])
    
    @router.post("/", response_model=ResponseDTO)
    async def create_item(item: CreateDTO, db: AsyncSession = Depends(get_db)):
        return await crud_repo.create(db=db, obj_in=item)

    @router.get("/{id}", response_model=ResponseDTO)
    async def read_item(id: str, db: AsyncSession = Depends(get_db)):
        db_obj = await crud_repo.get(db=db, id=id)
        if not db_obj:
            raise HTTPException(status_code=404, detail="Not found")
        return db_obj
        
    # 同理處理 GET (multi), PUT (update), DELETE (remove)

    return router
```
* **架構價值**: 到此階段，每新增一個 JSON 檔案，系統就能不編寫任何一行新程式，自動產生對應的 Database Model 以及擁有完整參數驗證的 `/create`, `/read`, `/update`, `/delete` API Endpoint。

## Task 2.3: 系統啟動與註冊機制 (App Lifecycle Management)

使用 FastAPI 原生的 `lifespan` 來控管「讀取 -> 生成 -> 註冊」流程，這保證了在接受外部請求前，記憶體中的反射類別皆已準備就緒。

### 2.3.1 Lifespan 註冊流
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 讀取並驗證 ./blueprints 目錄下的所有 JSON 檔案
    # 2. 為每一個 blueprint 調用 Dynamic ORM Factory 生成 SQLAlchemy 實體
    # 3. 為每一個 blueprint 調用 Dynamic DTO Factory 生成 Pydantic 實體
    # 4. 實例化 Generic Repository
    # 5. 調用 Router Builder 生成 APIRouter
    # 6. app.include_router(router) 將路由綁定至主程
    
    # 註: 此階段若拋錯，應用會強制中斷，確保不帶著有瑕疵的模型上線
    yield
    
    # Shutdown events... (如關閉 DB ThreadPool 等)

app = FastAPI(lifespan=lifespan)
```

### 反射限制注意事項
FastAPI 對於 `openapi.json` 的產生，主要依賴於應用啟動時的 Router 綁定。如果在啟動後 (Runtime) 臨時新增 Router，是不會即時更新 Swagger 介面的，因此本系統的設計前提是：**修改或新增 JSON Blueprints 之後，需要對系統進度熱重載或重啟 (Restart) 以反映變更。**
