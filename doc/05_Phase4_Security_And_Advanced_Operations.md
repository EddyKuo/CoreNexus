# Phase 4: 邊界防禦與進階查詢 (Security & Advanced Operations)

標準的 CRUD 在企業級應用中極少單獨存在。列表 API 除了列出所有資料，還必須包含過濾、排序與分頁；而敏感資料也必須受到權限控制。這必須是在生成引擎架構下自動解構並實現的。

## Task 4.1: 動態查詢過濾器 (Dynamic Query Builder)

由於我們的模型是動態的，過濾條件無法寫死。系統需要具備解析 URL Query Parameters 並將其轉換為 SQLAlchemy filter 的翻譯器。

### 4.1.1 魔法參數解析 (Magic Filter Protocol)
借鏡 Django ORM 的風格，使用雙底線 `__` 作為運算子。
介面範例: `GET /users?age__gte=18&name__icontains=admin&status=active`

**實作機制：**
1. 攔截 API 的 `@router.get` 中傳入的 `request.query_params`。
2. 開發 `QueryTransformer`：
```python
def parse_filters(model: Type[DeclarativeBase], query_params: dict):
    filters = []
    for key, value in query_params.items():
        if '__' in key:
            field_name, operator = key.split('__', 1)
        else:
            field_name, operator = key, 'eq'
            
        column = getattr(model, field_name, None)
        if not column:
            continue # 保留為其他參數或直接忽略
            
        if operator == 'eq':
            filters.append(column == value)
        elif operator == 'gt':
            filters.append(column > value)
        elif operator == 'gte':
            filters.append(column >= value)
        elif operator == 'icontains':
            filters.append(column.ilike(f"%{value}%"))
        # 擴充：in, lt, lte 等...
        
    return filters
```

## Task 4.2: 動態排序與分頁 (Sorting & Pagination)

前端串接資料表時，絕對依賴規律對稱的分頁封包格式，不應每張表格式不一。

### 4.2.1 統一響應封包 (Standard Pagination Meta)
動態生成 Response DTO 時，可以再包裝一層 `PaginationSchema[T]`。
```python
{
  "total": 125,
  "pages": 13,
  "current_page": 1,
  "per_page": 10,
  "data": [ ... ] // 這裡才是自動生成的模型列表
}
```

### 4.2.2 排序解析器 (Sort Protocol)
支援以 `,` 隔開，並以 `-` 符號標示反向排序。
介面範例: `GET /users?sort=-created_at,role`

系統將自動映射為 SQLAlchemy 的 `.order_by(desc(User.created_at), asc(User.role))`。

## Task 4.3: 基礎攔截器與權限擴展點 (Middleware & Auth Hooks)

在藍圖 (JSON) 中，開發者可能會標註 `"auth_required": true`。在動態生成 Router 的過程中，工廠函數需要依賴這個 metadata 決定是否替這條路由插入攔截器。

### 4.3.1 OpenAPI 友好的依賴注入機制 (Dependency Injection)
```python
def build_route_dependencies(schema: ModelSchema):
    deps = []
    if schema.auth_required:
        # get_current_user 中實作 JWT 校驗邏輯
        deps.append(Depends(get_current_user))
    # 也可以預留 RBAC 的設定，例如 schema.required_roles
    return deps
```
綁定至 Router:
```python
dependencies = build_route_dependencies(model_schema)

@router.delete("/{id}", dependencies=dependencies) # 這樣 API Explorer 就會自動打上鎖頭圖示
async def delete_item(id: str, db: AsyncSession = Depends(get_db)):
    ...
```
這種設計使得資安控制被「向後推移」到了 JSON 配置層，系統架構完全解耦，實體程式碼極度乾淨。
