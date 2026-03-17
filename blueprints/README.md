# Meta-System 藍圖規範 (Blueprints Definition)

本目錄 (`blueprints/`) 是整個 Meta-System 的「單一事實來源 (Single Source of Truth)」。所有的資料庫實體、傳輸物件 (DTOs)、以及 CRUD API Endpoints 都是基於這裡的 JSON 檔案所動態生成的。

因為 JSON 格式本身不支援註解，我們透過這份文件來解釋藍圖中各欄位的意義與規範。

## 藍圖核心結構 (Core Structure)

一份標準的 Blueprint JSON 包含以下主要區塊：

```json
{
  "model_name": "User",                   // [必填] 應用程式內部使用的類別名稱 (請使用 PascalCase)
  "table_name": "users",                  // [必填] 寫入關聯式資料庫的實體表名稱 (請使用 snake_case)
  "description": "System User Account",   // [選填] 模型的描述，將用於 Swagger UI 的 API 文檔說明
  "auth_required": true,                  // [選填] 決定此模型的 API 是否需要 JWT 權限驗證 (預設 false)
  "fields": [ ... ],                      // [必填] 欄位陣列，定義資料表的每一欄
  "relations": [ ... ]                    // [選填] 關聯陣列，定義與其他 Table 的 ORM 關係
}
```

## 欄位定義規範 (Fields Definition)

`fields` 陣列中的每一個物件代表一個屬性（Column）。

| 屬性名稱 | 型別 | 必填 | 說明 |
| :--- | :--- | :---: | :--- |
| `name` | string | ✅ | 欄位名稱 (使用 snake_case)。 |
| `type` | string | ✅ | 抽象資料型態。支援：`string`, `text`, `integer`, `float`, `boolean`, `datetime`, `uuid`, `json`。 |
| `primary_key`| boolean| ❌ | 標註是否為主鍵，預設為 `false`。每個 Table 必須至少有一個 primary key 欄位。 |
| `nullable` | boolean| ❌ | 標註是否允許為 NULL，預設為 `true`。(若是 Primary Key 則強制為 false)。 |
| `unique` | boolean| ❌ | 是否加上唯一約束限制 (Unique Index)，預設為 `false`。 |
| `index` | boolean| ❌ | 是否為此欄位建立普通索引以加速查詢，預設為 `false`。 |
| `length` | integer| ❌ | 針對 `string` 類型限制最大長度（如 VARCHAR(255)）。 |
| `default` | any | ❌ | 預設值。支援直接賦值（如 `18`, `true`），或特殊保留字（如 `"uuid4"` 產生 UUID, `"now"` 產生當下系統時間）。 |
| `description`| string | ❌ | 該欄位的用途描述，將同步反映在 DB Column Comment 以及 API Schema 中。 |

### `type` 的底層映射對照

開發藍圖時使用的是「抽象型態」，引擎在啟動時會根據以下規則進行映射：

*   `uuid` ➜ SQLAlchemy `UUID` ➜ Pydantic `UUID4`
*   `string` ➜ SQLAlchemy `String(length)` ➜ Pydantic `str`
*   `text` ➜ SQLAlchemy `Text` ➜ Pydantic `str`
*   `integer` ➜ SQLAlchemy `Integer` ➜ Pydantic `int`
*   `float` ➜ SQLAlchemy `Float` ➜ Pydantic `float`
*   `boolean` ➜ SQLAlchemy `Boolean` ➜ Pydantic `bool`
*   `datetime` ➜ SQLAlchemy `DateTime(timezone=True)` ➜ Pydantic `datetime`
*   `json` ➜ SQLAlchemy `JSON` ➜ Pydantic `dict | list`

## 關聯定義規範 (Relations Definition)

`relations` 用以描述模型之間的關係，以便 ORM 進行 Join 查詢。

| 屬性名稱 | 型別 | 必填 | 說明 |
| :--- | :--- | :---: | :--- |
| `name` | string | ✅ | 在 ORM 實體中存取的關聯屬性名稱。 |
| `type` | string | ✅ | 關聯類型。目前支援 `"one-to-many"`, `"many-to-one"`, `"one-to-one"`, `"many-to-many"`。 |
| `target_model`| string | ✅ | 目標關聯的模型名稱（即對方的 `model_name`，如 `"Post"`）。 |
| `back_populates`| str | ❌ | 在目標模型中，反向指向回來的屬性名稱（用於維持雙向同步）。 |

## 範例：User Authentication Blueprint

請參考 `user_auth.json`，它展示了：
1. 如何使用 UUID 作為主鍵 (`default: "uuid4"`)。
2. 如何對登入帳號建立唯一約束 (`unique: true`)。
3. 如何設定預設布林值 (`default: true` on `is_active`)。
4. 如何自動寫入建立時間 (`default: "now"` on `created_at`)。
5. 如何封鎖匿名存取 (`auth_required: true`)。
6. 如何宣示與貼文 (Posts) 的一對多關聯關係。
