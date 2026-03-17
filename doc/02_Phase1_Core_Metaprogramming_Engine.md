# Phase 1: 基礎維度建構 (Core Metaprogramming Engine)

此階段著重於：藍圖定義語法（DSL）、藍圖解析檢驗、以及將靜態文件轉換為執行期反射（Reflection）類別。

## Task 1.1: 確立 JSON Schema 規範 (Schema Definition Protocol)

為確保系統的延展性，必須定義出我們自有的「Meta-Schema」（即描述 Schema 的 Schema）。

### 1.1.1 JSON 藍圖結構設計
藍圖將由頂層元資料 (Metadata) 與欄位清單 (Fields) 組成。

```json
{
  "model_name": "User",                   // 程式內部類別名稱 (PascalCase)
  "table_name": "users",                  // 物理資料表名稱 (snake_case)
  "description": "System User Account",   // 將映射到 API 文檔或 DB Comment
  "auth_required": true,                  // 預留給 Phase 4 的權限鎖定機制
  "fields": [
    {
      "name": "id",
      "type": "uuid",                     // 統一抽象型態，非底層 DB 型態
      "primary_key": true,
      "default": "uuid4"
    },
    {
      "name": "email",
      "type": "string",
      "length": 255,
      "unique": true,
      "nullable": false,
      "index": true,
      "description": "Login Email"
    },
    {
      "name": "age",
      "type": "integer",
      "default": 18
    }
  ],
  "relations": [
    {
      "name": "posts",
      "type": "one-to-many",
      "target_model": "Post",
      "back_populates": "author"
    }
  ]
}
```

### 1.1.2 抽象型態定義 (Abstract Data Types)
定義 JSON 中可用的抽象欄位 `type`，後續引擎會根據此映射表分配具體型態：
- `string`: 映射為 SQL `VARCHAR` / Pydantic `str`
- `text`: 映射為 SQL `TEXT` / Pydantic `str`
- `integer`: 映射為 SQL `INTEGER` / Pydantic `int`
- `float`: 映射為 SQL `FLOAT` / Pydantic `float`
- `boolean`: 映射為 SQL `BOOLEAN` / Pydantic `bool`
- `datetime`: 映射為 SQL `TIMESTAMP WITH TIME ZONE` / Pydantic `datetime`
- `uuid`: 映射為 SQL `UUID` / Pydantic `UUID4`
- `json`: 映射為 SQL `JSONB` / Pydantic `dict | list`

## Task 1.2: 實作 Schema 解析與校驗器 (Schema Parser & Validator)

這是一道防線，運用 Pydantic 本身來確保「載入的 JSON 藍圖」是正確的。

### 1.2.1 內部校驗模型 (Meta Models)
負責讀取 JSON 前先由 Python 內部檢查。

```python
from pydantic import BaseModel, Field

class FieldSchema(BaseModel):
    name: str
    type: str # 需限制在合法 Enum 內
    primary_key: bool = False
    unique: bool = False
    nullable: bool = True
    length: int | None = None
    default: Any | None = None
    index: bool = False

class RelationSchema(BaseModel):
    name: str
    type: Literal["one-to-one", "one-to-many", "many-to-many"]
    target_model: str
    back_populates: str | None = None

class ModelSchema(BaseModel):
    model_name: str
    table_name: str
    fields: list[FieldSchema]
    relations: list[RelationSchema] = []
```
* **職責**: 啟動時掃描 `blueprints/` 資料夾，若 JSON 少漏必要屬性，直接拋出 `SystemExit` 拒絕啟動。

## Task 1.3: 實作動態 ORM 生成器 (Dynamic SQLAlchemy Factory)

運用 Python 的 `type()` 動態類別生成技術。

### 1.3.1 型別對應轉換工坊
將 Abstract Type 對應至 SQLAlchemy Column。

```python
# 概念設計
def get_sa_column(field: FieldSchema):
    sa_type = TYPE_MAPPING[field.type]
    if field.length and field.type == 'string':
        sa_type = String(length=field.length)
        
    return mapped_column(
        sa_type,
        primary_key=field.primary_key,
        nullable=field.nullable,
        unique=field.unique,
        index=field.index,
        # ... default 處理 (callable 等)
    )
```

### 1.3.2 類別反射機制
```python
def create_sa_model(schema: ModelSchema, Base):
    attrs = {"__tablename__": schema.table_name}
    for f in schema.fields:
        attrs[f.name] = get_sa_column(f)
        
    # Phase 1 進階：處理 relationship() 動態關聯綁定
    # ...
    
    # 產生類別並註冊在 MetaData
    return type(schema.model_name, (Base,), attrs)
```

## Task 1.4: 實作動態 DTO 生成器 (Dynamic Pydantic Factory)

根據同一份 JSON 模型，利用 `pydantic.create_model` 來產生 3 種面向 API 的 DTO：

```python
from pydantic import create_model

def create_dtos_for_model(schema: ModelSchema):
    # 1. CreateSchema: 排除 ID, Auto-generated fields 
    create_fields = {}
    for f in schema.fields:
        if not f.primary_key:
            # (型別, 預設值) tuple 傳給 create_model
            create_fields[f.name] = (PYDANTIC_TYPE_MAPPING[f.type], ...) 
            # 處理 Optional 或 default...
            
    CreateDTO = create_model(f"{schema.model_name}Create", **create_fields)
    
    # 2. UpdateSchema: 所有欄位皆為 Optional, 並排除不可變欄位 (如 ID)
    # 3. ResponseSchema: 包含 ID，並開啟 from_attributes = True 給 ORM
    
    return CreateDTO, UpdateDTO, ResponseDTO
```
* **架構價值**: 此一產出使得下一階段 (Phase 2) 的 FastAPI 能夠自動進行 Request Body 檢驗以及產生漂亮的 Swagger UI。
