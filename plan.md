# 專案實作計畫 (Project Implementation Plan)

這份計畫基於系統分析文件，依序展開實作的每個步驟（Work Breakdown Structure）。我們將按照 Phase 1 到 Phase 5 的順序，逐步建立這個 Meta-System。

## Phase 1: 基礎維度建構 (Core Metaprogramming Engine)
- [ ] **1.1 初始化專案結構**: 建立目錄結構 (例如 `blueprints/`, `src/core/`)，設定環境依賴 (`fastapi`, `sqlalchemy`, `pydantic`, `alembic`, `asyncpg`)。
- [ ] **1.2 確立 JSON Schema 規範**: 定義並建立 Pydantic Meta-Schema (`src/core/models/schema_def.py`)，包含 `FieldSchema`, `RelationSchema`, `ModelSchema`。
- [ ] **1.3 實作 Schema Parser**: 撰寫解析器 (`src/core/parser.py`)，負責讀取並校驗 `blueprints/*.json` 的內容正確性。
- [ ] **1.4 實作動態 ORM 生成器**: 開發工廠函數 (`src/core/factory/orm_factory.py`)，將抽象型別映射為 SQLAlchemy Columns，動態建立 Model 類別。
- [ ] **1.5 實作動態 DTO 生成器**: 開發工廠函數 (`src/core/factory/dto_factory.py`)，依據上述模型產出對應的 API Create/Update/Response Pydantic Models。
- [ ] **1.6 [驗證]**: 撰寫基礎單元測試，確保給定標準 JSON，引擎能正確吐出 SQLAlchemy Model 與 Pydantic Model 類別。

## Phase 2: 觀測通道映射 (Dynamic Routing & API Integration)
- [ ] **2.1 實作通用資料存取層 (Generic Repository)**: 撰寫 `src/core/repository.py`，封裝基於 `AsyncSession` 的通用 CRUD 操作。
- [ ] **2.2 實作動態路由工廠 (Router Builder)**: 開發 `src/core/router_builder.py`，負責將 ORM Model, DTOs 與 Generic Repository 綁定進 `APIRouter`。
- [ ] **2.3 實作系統啟動機制 (App Lifespan)**: 於 `src/main.py` 中實作 FastAPI 的 lifespan event，在啟動階段載入藍圖並動態掛載路由。
- [ ] **2.4 [驗證]**: 提供基礎藍圖並啟動 FastAPI，確保能在 `/docs` (Swagger UI) 看到自動生成的完整 API 端點並能成功發送基礎請求。

## Phase 3: 時間軸與狀態演進 (Database Migration Strategy)
- [ ] **3.1 整合與初始化 Alembic**: 建立遷移目錄設定。
- [ ] **3.2 修改 `env.py` 動態掛載**: 調整 Alembic 環境，讓它能在背景載入 JSON 藍圖並獲取動態生成的 `Base.metadata` 結構。
- [ ] **3.3 實作自動化遷移指令 (Auto-Migration CLI)**: 建立命令列腳本 (`cli.py`)，封裝 `alembic revision --autogenerate` 和 `alembic upgrade head`。
- [ ] **3.4 實作安全防禦鉤子 (Safe-Mode)**: 在腳本產出後加入靜態分析，偵測到 `drop_column`/`drop_table` 操作時拋出警告，防止資料誤刪。
- [ ] **3.5 [驗證]**: 修改 JSON 藍圖（如新增欄位），執行 CLI 工具，並檢查 DB 實體 Table 是否成功增加該欄位。

## Phase 4: 邊界防禦與進階查詢 (Security & Advanced Operations)
- [ ] **4.1 實作動態查詢過濾器**: 新增 `src/core/utils/query_builder.py`，解析 URL 中的 `__gte`, `__icontains` 等參數，轉換為 PostgreSQL filter。
- [ ] **4.2 實作動態排序與統一分頁**: 建構統一的分頁 Response DTO (`PaginationSchema`)，並於路由層實現分頁邏輯與 `sort` 參數解析。
- [ ] **4.3 實作基礎攔截器與權限擴展點**: 於動態路徑工廠中預留 FastAPI `Depends` 接口，使標記有 `auth_required: true` 的藍圖能自動啟用認證。
- [ ] **4.4 [驗證]**: 測試帶有複雜查詢條件與分頁參數的 API，確保 SQL 產生結果精確符合預期。

## Phase 5: 封裝與交付 (Production Readiness)
- [ ] **5.1 異步資料庫連線池優化**: 調校 `create_async_engine` 參數，設定妥當的 pool_size 與 timeout。
- [ ] **5.2 實作全域錯誤處理**: 添加 Exception Handler 攔截 `IntegrityError` 等底層錯誤並轉換為標準 400/409 HTTP Response。
- [ ] **5.3 容器化與範例建置**: 撰寫 `Dockerfile` 及 `docker-compose.yml`，並於 `examples/` 配置實際的業務場景藍圖。
- [ ] **5.4 [驗證]**: `docker-compose up` 一鍵啟動成功，所有機能正常運作。
