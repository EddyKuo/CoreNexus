# CoreNexus

**CoreNexus** 是一個強大的 **Meta-System Code Generation Engine (中介系統程式碼生成引擎)**，基於 SSOT (Single Source of Truth, 單一真值來源) 架構設計。

**核心概念**：你只需要寫一份 YAML 設定檔（藍圖），系統就會在啟動時自動生成：
- 資料庫模型（SQLAlchemy ORM）
- 資料驗證模型（Pydantic DTOs）
- 完整的 REST API 路由（FastAPI）
- 資料庫遷移腳本（Alembic）

---

## 目錄

1. [專案目的](#專案目的)
2. [從零理解這個專案](#從零理解這個專案)
3. [快速開始](#快速開始)
4. [如何建立新的 API](#如何建立新的-api)
5. [如何加入自訂商業邏輯](#如何加入自訂商業邏輯)
6. [如何修改現有的 API](#如何修改現有的-api)
7. [藍圖欄位完整說明](#藍圖欄位完整說明)
8. [資料流與系統架構](#資料流與系統架構)
9. [目錄結構說明](#目錄結構說明)
10. [常用指令](#常用指令)
11. [技術棧](#技術棧)
12. [實作進度](#實作進度)

---

## 專案目的

傳統開發新增一個資料表，你需要手動寫：

```
手動寫 → Alembic 遷移檔
手動寫 → SQLAlchemy Model
手動寫 → Pydantic DTO (Request/Response)
手動寫 → FastAPI Router (GET/POST/PATCH/DELETE)
```

**CoreNexus 的目標**：上面這四步，你只要寫一份 YAML 檔，其餘全部自動完成。

---

## 從零理解這個專案

### 第一步：理解「藍圖」是什麼

藍圖（Blueprint）就是一份 YAML 設定檔，放在 `blueprints/` 目錄下。每一份藍圖代表你系統中的一個「資料實體」（例如：使用者、訂單、商品）。

最簡單的藍圖範例：

```yaml
# blueprints/product.yaml
model_name: Product          # Python 類別名稱（PascalCase）
table_name: products         # 資料庫表名（snake_case）
description: 商品目錄
auth_required: false         # 不需要登入就能存取

fields:
  - name: id
    type: uuid
    primary_key: true
    default: uuid4           # 自動產生 UUID

  - name: name
    type: string
    length: 255
    nullable: false

  - name: price
    type: float
    nullable: false

  - name: created_at
    type: datetime
    default: now             # 自動填入當下時間
```

### 第二步：理解系統啟動時發生什麼

```
你的 product.yaml
      ↓
  parser.py 讀取並驗證 YAML 格式是否正確
      ↓
  orm_factory.py 動態建立 SQLAlchemy Model（等同手寫 class Product(Base): ...）
      ↓
  dto_factory.py 動態建立三個 Pydantic 模型：
                   - ProductCreate（新增用）
                   - ProductUpdate（修改用）
                   - ProductResponse（回傳用）
      ↓
  router_builder.py 動態建立 FastAPI 路由：
                   GET    /api/v1/products          列出所有
                   GET    /api/v1/products/{id}     取得單筆
                   POST   /api/v1/products          新增
                   PATCH  /api/v1/products/{id}     修改
                   DELETE /api/v1/products/{id}     刪除
      ↓
  main.py 的 lifespan 事件把路由掛載到 FastAPI App
      ↓
  http://localhost:8000/docs 可以直接看到並測試 API！
```

### 第三步：理解目錄職責

| 目錄/檔案 | 你需要關心嗎？ | 說明 |
|---|---|---|
| `blueprints/` | ✅ **主要工作區** | 你的 YAML 藍圖都放這裡 |
| `src/main.py` | 偶爾 | 啟動入口，掛載自訂路由時需要編輯 |
| `src/core/` | 極少 | 引擎核心，通常不需要修改 |
| `alembic/` | 自動 | 資料庫遷移，透過 CLI 指令操作 |
| `cli.py` | 指令操作 | 安全遷移工具 |
| `tests/` | 測試時 | 單元與整合測試 |

---

## 快速開始

### 前置需求

- Python 3.11+
- PostgreSQL 15+（或使用 Docker）
- Git

### 步驟 1：複製專案

```bash
git clone <你的 repo URL>
cd CoreNexus
```

### 步驟 2：建立虛擬環境

```bash
# 建立虛擬環境
python -m venv .venv

# 啟用（Linux / macOS）
source .venv/bin/activate

# 啟用（Windows CMD）
.venv\Scripts\activate.bat

# 啟用（Windows PowerShell）
.venv\Scripts\Activate.ps1
```

### 步驟 3：安裝相依套件

```bash
pip install -r requirements.txt
```

若 `requirements.txt` 不存在，手動安裝：

```bash
pip install fastapi sqlalchemy alembic pydantic asyncpg uvicorn python-dotenv
```

### 步驟 4：設定環境變數

複製範例環境變數檔：

```bash
cp .env.example .env
```

編輯 `.env`，填入你的 PostgreSQL 連線資訊：

```env
DATABASE_URL=postgresql+asyncpg://帳號:密碼@localhost:5432/資料庫名稱

# 範例（本機 PostgreSQL）
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/corenexus
```

### 步驟 5：使用 Docker 快速啟動資料庫（可選）

如果你沒有安裝 PostgreSQL，使用 Docker：

```bash
docker-compose up -d postgres
```

### 步驟 6：初始化資料庫

```bash
# 產生第一份資料庫遷移腳本
python cli.py migrate --message "initial schema"

# 套用遷移，建立資料表
alembic upgrade head
```

### 步驟 7：啟動開發伺服器

```bash
uvicorn src.main:app --reload
```

成功後，開啟瀏覽器：

- **Swagger UI（互動式 API 文件）**：http://localhost:8000/docs
- **ReDoc（閱讀版 API 文件）**：http://localhost:8000/redoc
- **健康檢查**：http://localhost:8000/health

---

## 如何建立新的 API

建立新 API 只需要三步驟：

### 步驟 1：在 `blueprints/` 新增 YAML 檔案

```bash
# 建立新藍圖（例如：商品管理）
touch blueprints/product.yaml
```

```yaml
# blueprints/product.yaml
model_name: Product
table_name: products
description: 電商商品目錄
auth_required: false

fields:
  - name: id
    type: uuid
    primary_key: true
    default: uuid4

  - name: name
    type: string
    length: 255
    nullable: false
    index: true
    description: 商品名稱

  - name: description
    type: text
    nullable: true
    description: 商品詳細描述

  - name: price
    type: float
    nullable: false
    description: 售價

  - name: stock
    type: integer
    default: 0
    description: 庫存數量

  - name: is_available
    type: boolean
    default: true
    description: 是否上架

  - name: created_at
    type: datetime
    default: now
    nullable: false
```

### 步驟 2：產生資料庫遷移

```bash
python cli.py migrate --message "add products table"
alembic upgrade head
```

### 步驟 3：重啟伺服器

```bash
uvicorn src.main:app --reload
```

**完成！** 前往 http://localhost:8000/docs，你會看到以下 API 已自動建立：

```
GET    /api/v1/products              取得商品列表（支援分頁與篩選）
GET    /api/v1/products/{id}         取得單一商品
POST   /api/v1/products              新增商品
PATCH  /api/v1/products/{id}         修改商品
DELETE /api/v1/products/{id}         刪除商品
```

---

## 如何加入自訂商業邏輯

當自動生成的 CRUD API 不夠用時，你可以加入自己的客製邏輯。

### 方法一：建立獨立 Router 模組（推薦）

適合較複雜的商業邏輯。

```bash
mkdir -p src/routers
touch src/routers/analytics.py
```

```python
# src/routers/analytics.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db

router = APIRouter(prefix="/analytics", tags=["Analytics 分析報表"])

@router.get("/revenue-summary")
async def get_revenue_summary(
    db: AsyncSession = Depends(get_db)
):
    """取得月營收摘要"""
    # 在這裡撰寫你的 SQL 查詢邏輯
    return {
        "status": "success",
        "data": {
            "monthly_revenue": 150000,
            "total_orders": 320
        }
    }

@router.get("/top-products")
async def get_top_products(
    limit: int = 10,
    db: AsyncSession = Depends(get_db)
):
    """取得銷售排行前 N 名商品"""
    # 你的查詢邏輯
    return {"products": []}
```

然後在 `src/main.py` 的 lifespan 結束後掛載：

```python
# src/main.py
from src.routers.analytics import router as analytics_router

# 在 app 建立後加入這行
app.include_router(analytics_router, prefix="/api/v1")
```

### 方法二：在藍圖中啟用身份驗證保護

在藍圖中設定 `auth_required: true`，系統會自動為該資源的所有 API 加上 JWT 驗證：

```yaml
# blueprints/user_profile.yaml
model_name: UserProfile
table_name: user_profiles
auth_required: true    # 所有 CRUD 路由都需要有效的 JWT Token

fields:
  - name: id
    type: uuid
    primary_key: true
    default: uuid4
  # ... 其他欄位
```

### 方法三：快速定義單一端點（適合測試）

```python
# src/main.py
@app.get("/api/v1/health-check", tags=["System"])
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
```

---

## 如何修改現有的 API

### 情境 1：新增欄位到現有資料表

編輯對應的 YAML 檔案：

```yaml
# blueprints/product.yaml（修改前）
fields:
  - name: name
    type: string
    length: 255

# 新增 category_id 欄位（修改後）
fields:
  - name: name
    type: string
    length: 255

  - name: category_id    # 新增這個欄位
    type: uuid
    nullable: true
    description: 商品分類 ID
```

然後執行遷移：

```bash
python cli.py migrate --message "add category_id to products"
alembic upgrade head
```

重啟伺服器後，API 的 Request/Response Schema 會自動包含新欄位。

### 情境 2：移除欄位（謹慎操作！）

CoreNexus 的 **Safe-Mode** 會偵測到 `drop_column`/`drop_table` 操作並阻止執行，防止意外刪除資料。

若確定要移除，需加上 `--force` 旗標（會顯示確認警告）：

```bash
python cli.py migrate --message "remove deprecated field" --force
```

### 情境 3：修改欄位屬性

直接修改 YAML 後重新遷移：

```yaml
# 把 length 從 100 改成 255
- name: title
  type: string
  length: 255    # 原本是 100
  nullable: false
```

### 情境 4：調整 API 是否需要身份驗證

```yaml
# 從公開改為需要登入
auth_required: true   # 改成 true

# 從需要登入改為公開
auth_required: false  # 改成 false
```

重啟伺服器即生效，無需遷移。

---

## 藍圖欄位完整說明

### 頂層設定

```yaml
model_name: Product        # [必填] Python 類別名稱，使用 PascalCase（如 UserProfile）
table_name: products       # [必填] 資料庫表名，使用 snake_case（如 user_profiles）
description: 商品說明      # [選填] 顯示於 Swagger 文件的說明
auth_required: false       # [選填] 是否需要 JWT 驗證，預設 false
```

### fields（欄位）屬性

| 屬性 | 類型 | 必填 | 說明 |
|---|---|:---:|---|
| `name` | string | ✅ | 欄位名稱，使用 snake_case |
| `type` | string | ✅ | 資料型別（見下方對照表） |
| `primary_key` | boolean | | 是否為主鍵，預設 false |
| `nullable` | boolean | | 是否允許 NULL，預設 true |
| `unique` | boolean | | 是否唯一，預設 false |
| `index` | boolean | | 是否建立索引加速查詢，預設 false |
| `length` | integer | | string 型別的最大字元長度 |
| `default` | any | | 預設值，支援 `"uuid4"`、`"now"` 或自訂值 |
| `foreign_key` | string | | 外鍵，格式：`表名.欄位名`（如 `users.id`） |
| `description` | string | | 欄位說明，顯示於 Swagger |

### 資料型別對照表

| 藍圖 type | SQLAlchemy | Pydantic | PostgreSQL |
|---|---|---|---|
| `uuid` | UUID | UUID4 | UUID |
| `string` | String(length) | str | VARCHAR |
| `text` | Text | str | TEXT |
| `integer` | Integer | int | INTEGER |
| `float` | Float | float | FLOAT |
| `boolean` | Boolean | bool | BOOLEAN |
| `datetime` | DateTime(timezone=True) | datetime | TIMESTAMPTZ |
| `json` | JSON | dict \| list | JSONB |

### relations（關聯）屬性

| 屬性 | 類型 | 必填 | 說明 |
|---|---|:---:|---|
| `name` | string | ✅ | ORM 關聯屬性名稱 |
| `type` | string | ✅ | 關聯類型：`one-to-many`、`many-to-one`、`one-to-one`、`many-to-many` |
| `target_model` | string | ✅ | 對應目標的 model_name |
| `back_populates` | string | | 對方模型中的反向屬性名稱 |

### 完整範例：含關聯的用戶與文章

```yaml
# blueprints/user_auth.yaml
model_name: User
table_name: users
description: System User Account
auth_required: true

fields:
  - name: id
    type: uuid
    primary_key: true
    default: uuid4

  - name: email
    type: string
    length: 255
    unique: true         # Email 不可重複
    nullable: false
    index: true          # 建立索引加速查詢
    description: 登入用 Email

  - name: hashed_password
    type: string
    length: 255
    nullable: false

  - name: full_name
    type: string
    length: 100
    nullable: true

  - name: is_active
    type: boolean
    default: true

  - name: created_at
    type: datetime
    default: now
    nullable: false

relations:
  - name: posts
    type: one-to-many    # 一個用戶有多篇文章
    target_model: Post
    back_populates: author
```

```yaml
# blueprints/blog_post.yaml
model_name: Post
table_name: posts
description: Blog Post
auth_required: true

fields:
  - name: id
    type: uuid
    primary_key: true
    default: uuid4

  - name: title
    type: string
    length: 255
    nullable: false
    index: true

  - name: body
    type: text
    nullable: false

  - name: published
    type: boolean
    default: false

  - name: author_id
    type: uuid
    nullable: false
    index: true
    foreign_key: users.id   # 外鍵關聯 users 表

  - name: created_at
    type: datetime
    default: now
    nullable: false

relations:
  - name: author
    type: many-to-one    # 多篇文章對應一個作者
    target_model: User
    back_populates: posts
```

---

## 資料流與系統架構

```
blueprints/*.yaml
       │
       ▼
  parser.py          ← 讀取並驗證 YAML 格式正確性（Fail-Fast 保護）
       │
       ▼
  orm_factory.py     ← 動態建立 SQLAlchemy Model 類別
       │                  等同手寫：class Product(Base): id = Column(UUID, ...)
       ▼
  dto_factory.py     ← 動態建立 Pydantic DTO 類別
       │                  ProductCreate、ProductUpdate、ProductResponse
       ▼
  router_builder.py  ← 動態建立 FastAPI APIRouter
       │                  GET /products、POST /products、PATCH /products/{id} ...
       ▼
  main.py lifespan   ← 系統啟動時執行上述流程，全部掛載到 FastAPI App
       │
       ▼
  http://localhost:8000/docs  ← 直接看到並測試 API！
```

### Fail-Fast 保護機制

如果任何一份藍圖格式有誤（缺少必填欄位、型別錯誤），系統會在啟動時立即拋出錯誤並終止，**絕對不會讓有問題的服務對外開放**。

### Safe-Mode 遷移保護

執行資料庫遷移時，CLI 會分析 Alembic 自動生成的腳本，若偵測到以下危險操作，會立即阻止並提示你確認：

- `op.drop_column(...)` — 刪除欄位
- `op.drop_table(...)` — 刪除資料表

---

## 目錄結構說明

```
CoreNexus/
├── blueprints/              ← 你的主要工作區！YAML 藍圖都放這裡
│   ├── user_auth.yaml       ← 用戶認證模組範例
│   ├── blog_post.yaml       ← 部落格文章範例
│   ├── product.yaml         ← 商品模組範例
│   └── README.md            ← 藍圖欄位詳細說明文件
│
├── src/
│   ├── main.py              ← FastAPI 程式進入點，掛載自訂路由時編輯此檔
│   ├── database.py          ← 資料庫連線設定（通常不需要改）
│   ├── core/
│   │   ├── parser.py        ← 解析 YAML 藍圖（不需要改）
│   │   ├── repository.py    ← 通用 CRUD 操作邏輯（不需要改）
│   │   ├── router_builder.py← 動態路由建構器（不需要改）
│   │   ├── auth.py          ← JWT 認證模組（可擴充）
│   │   ├── models/
│   │   │   └── schema_def.py← 藍圖的 Pydantic Meta-Schema
│   │   ├── factory/
│   │   │   ├── orm_factory.py  ← SQLAlchemy 動態生成器
│   │   │   └── dto_factory.py  ← Pydantic 動態生成器
│   │   └── utils/
│   │       └── query_builder.py← 魔法查詢過濾器（?age__gte=18）
│   └── routers/             ← 你的自訂 Router 放這裡
│       └── analytics.py     ← 自訂分析報表 API 範例
│
├── alembic/                 ← 資料庫遷移設定（透過 CLI 操作）
│   └── versions/            ← 自動生成的遷移腳本存放處
├── alembic.ini              ← Alembic 設定檔
├── cli.py                   ← 安全遷移 CLI 工具
├── docker-compose.yml       ← Docker 一鍵啟動設定
├── .env                     ← 環境變數（不要 commit 到 Git！）
├── .env.example             ← 環境變數範本
├── requirements.txt         ← Python 套件依賴清單
└── tests/                   ← 測試檔案
```

---

## 常用指令

```bash
# ── 環境設定 ──────────────────────────────────
# 建立並啟用虛擬環境
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
.venv\Scripts\activate.bat         # Windows CMD

# 安裝套件
pip install -r requirements.txt

# ── 啟動服務 ──────────────────────────────────
# 開發模式（自動重載）
uvicorn src.main:app --reload

# 指定 port
uvicorn src.main:app --reload --port 8080

# ── 資料庫遷移 ────────────────────────────────
# 自動偵測變更並生成遷移腳本（Safe-Mode 保護）
python cli.py migrate --message "描述你的變更"

# 套用遷移到資料庫
alembic upgrade head

# 回滾到上一個版本
alembic downgrade -1

# 查看目前遷移狀態
alembic current

# 查看遷移歷史
alembic history

# ── 測試 ──────────────────────────────────────
# 執行所有測試
pytest

# 執行測試並顯示覆蓋率
pytest --cov=src

# ── Docker ────────────────────────────────────
# 啟動所有服務（PostgreSQL + App）
docker-compose up -d

# 只啟動資料庫
docker-compose up -d postgres

# 停止所有容器
docker-compose down
```

---

## 進階功能：魔法查詢過濾器

CoreNexus 內建動態查詢協定，讓你不需要寫任何程式碼，就可以對 API 做複雜的篩選：

```bash
# 取得年齡大於等於 18 的用戶
GET /api/v1/users?age__gte=18

# 取得名稱包含 "john"（不分大小寫）的用戶
GET /api/v1/users?full_name__icontains=john

# 取得今天之後建立的文章
GET /api/v1/posts?created_at__gte=2026-01-01

# 分頁查詢（第 2 頁，每頁 20 筆）
GET /api/v1/products?page=2&page_size=20

# 排序（依價格由低到高）
GET /api/v1/products?sort=price&order=asc
```

支援的過濾運算子：

| 運算子 | 說明 | 範例 |
|---|---|---|
| `__eq` | 等於（預設） | `?status__eq=active` |
| `__ne` | 不等於 | `?status__ne=deleted` |
| `__gt` | 大於 | `?age__gt=18` |
| `__gte` | 大於等於 | `?age__gte=18` |
| `__lt` | 小於 | `?price__lt=1000` |
| `__lte` | 小於等於 | `?price__lte=1000` |
| `__contains` | 包含（區分大小寫） | `?name__contains=John` |
| `__icontains` | 包含（不分大小寫） | `?name__icontains=john` |
| `__startswith` | 開頭為 | `?email__startswith=admin` |
| `__in` | 在清單中 | `?status__in=active,pending` |

---

## 技術棧

| 元件 | 技術 | 說明 |
|---|---|---|
| Web 框架 | FastAPI | ASGI，支援 async/await，自動生成 OpenAPI 文件 |
| ORM | SQLAlchemy 2.0 | AsyncSession 非同步操作，DeclarativeBase |
| 資料驗證 | Pydantic V2 | Request/Response Schema，自動驗證 |
| 資料庫遷移 | Alembic | 版本控制，Safe-Mode 保護 |
| 資料庫 | PostgreSQL 15+ | JSONB 支援，高效能 |
| DB 驅動 | asyncpg | 非同步 PostgreSQL 驅動 |

---

## 實作進度

> 目前專案處於規劃/文件階段，以下為各 Phase 的實作進度追蹤：

| Phase | 內容 | 狀態 |
|---|---|---|
| Phase 1 | Schema 定義、ORM Factory、DTO Factory | 未開始 |
| Phase 2 | Generic Repository、Router Builder、Lifespan 啟動 | 未開始 |
| Phase 3 | Alembic 整合、Safe-Mode 遷移 CLI | 未開始 |
| Phase 4 | 魔法查詢過濾器、分頁、Auth 擴展點 | 未開始 |
| Phase 5 | 連線池優化、全域錯誤處理、Docker 化 | 未開始 |

詳細的實作任務清單請參考 [plan.md](plan.md)。

---

## 常見問題 FAQ

**Q: 我修改了 YAML，為什麼 API 沒有更新？**

A: 需要重啟伺服器（`uvicorn src.main:app --reload`）。如果有新增/修改欄位，還需要先執行資料庫遷移。

**Q: Swagger UI 看不到我的新 API？**

A: 確認 YAML 格式正確（縮排用空格，不用 Tab），且 `model_name` 使用 PascalCase，`table_name` 使用 snake_case。

**Q: 遷移失敗，怎麼辦？**

A: 執行 `alembic current` 查看目前狀態，`alembic history` 查看遷移歷史，找到問題後修正 YAML 再重新遷移。

**Q: 如何在 API 中存取目前登入的用戶？**

A: 在自訂路由中使用 `Depends(verify_token)`，它會回傳 JWT Payload，其中包含用戶 ID 等資訊。

**Q: 可以同時有多個 YAML 藍圖嗎？**

A: 可以！`blueprints/` 目錄下的所有 YAML 檔案都會被自動載入。你可以查看現有的範例藍圖（如 `user_auth.yaml`、`blog_post.yaml` 等）來了解如何組織多個實體。

---

*Built with FastAPI & SQLAlchemy · CoreNexus Meta-System Code Generation Engine*
