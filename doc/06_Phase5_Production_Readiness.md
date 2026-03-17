# Phase 5: 封裝與交付 (Production Readiness)

最後一個階段，是要將這套設計從「強大的 Prototype」轉型成「能承載百萬請求的穩定基礎設施」。這包含了對底層細節的防守、資源效率的運用、以及最終的工程交付。

## Task 5.1: 異步資料庫連線池優化 (Async DB Pool Strategy)

由於我們全面使用 FastAPI + SQLAlchemy 異步操作 (AsyncSession)。傳統的同步驅動 (psycopg2) 在高併發時會成為瓶頸，我們必須配置 `asyncpg` 及高效連線池。

### 5.1.1 參數優化設計
當應用被容器化及水平擴展 (Horizontal Scaling) 多副本時，資料庫連線池是決定存活的關鍵：
```python
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    DATABASE_URL, # 採用 postgresql+asyncpg://
    pool_size=20, # 保持的暖連線數量
    max_overflow=10, # 在突發流量中允許超出的連線數
    pool_recycle=3600, # 一小時強制重啟連線，防範資料庫端主動斷線 (MySQL 較常發生, PG 也可依此防患未然)
    pool_timeout=30, # 若連線全被佔滿，等待的最高秒數
    pool_pre_ping=True # 每次從池中拿出連線時，先 ping 確認存活，防止使用死連線造成 500
)
```

## Task 5.2: 全域錯誤處理 (Global Exception Handling)

由於操作層次已被抽象化，我們無法在每一個 `try...except` 裡頭抓所有錯誤，必須在 FastAPI 設定全域例外攔截。

### 5.2.1 底層例外轉換 (Exception Translation)
當外部打入違反 Unique Index 或 Foreign Key 的資料：
1. SQLAlchemy 內部拋出 `IntegrityError`。
2. 如果沒有攔截，API 會噴出 500 Internal Server Error，並且暴露出資料表結構跟原始 SQL（有嚴重的資安/滲透風險）。
3. 透過全域攔截器：
```python
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

@app.exception_handler(IntegrityError)
async def sqlalchemy_integrity_error_handler(request: Request, exc: IntegrityError):
    # 分析錯誤源因 (如 Postgres 錯誤碼 23505 unique_violation)
    return JSONResponse(
        status_code=409,
        content={"error": "Resource Conflict", "detail": "資料約束發生衝突 (例如重複的唯一鍵值)。"}
    )
```

## Task 5.3: 容器化與展示交付 (Dockerization & Examples)

為確保其他開發團隊能夠在 5 分鐘內理解並啟動此Meta-System。

### 5.3.1 一鍵啟動拓譜 (Topology)
我們將提供 `docker-compose.yml`：
* **Service 1 - App**: 基於 `python:3.11-slim`，透過 `uvicorn main:app --workers 4` 啟動，自動掛載專案 `blueprints/` 供隨時修改。
* **Service 2 - DB**: 官方 `postgres:15-alpine`，包含初始帳號密碼，掛載持久化 Volume。

### 5.3.2 交付文件結構
系統應包含專門的 `/examples` 資料夾，放置具備指標性參考的 JSON Blueprints：
1. `ecommerce_product.json` (展現複雜的 Float 型態與欄位長度控制)。
2. `user_auth.json` (展現 `auth_required: true` 以及 UUID 作為 Primary Key 的情境)。
3. `blog_relations.json` (展現 one-to-many 關聯建立模式)。

透過這 5 個階段的解構，我們確立了一套極具擴充性、符合 Single Source of Truth 原則，並具備高度容錯防禦能力的生成引擎架構，為未來的靈活業務演進打下堅實基礎。
