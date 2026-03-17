# Meta-System (生成引擎) 系統分析與架構設計文件

本目錄包含了 Meta-System 生成引擎的完整系統分析與架構設計規範。
這是一套能夠從 JSON 結構藍圖 (Schema Blueprints) 中，在啟動期自動化生成對應之 ORM 資料庫模型、Pydantic 傳輸驗證物件、基礎 CRUD API 與 Swagger 文件、以及動態 Migration 降級防禦的基礎設施。

## 文件索引

1. **[01_System_Architecture_Vision.md](./01_System_Architecture_Vision.md)**
   > 系統願景、核心防禦架構原則(SSOT)、系統巨觀組件流向以及主要技術棧 (FastAPI + SQLAlchemy + Alembic) 的策略定義。

2. **[02_Phase1_Core_Metaprogramming_Engine.md](./02_Phase1_Core_Metaprogramming_Engine.md)**
   > 解構 JSON Schema 規範；詳細說明如何利用 Python Meta class `type()` 動態建立 SQLAlchemy Model，以及利用 `pydantic.create_model` 生產不同行為流的 DTO (Create/Update/Response)。

3. **[03_Phase2_Observation_Channel_Mapping.md](./03_Phase2_Observation_Channel_Mapping.md)**
   > 敘述 Generic Repository Pattern (通用的 CRUD 異步封裝) 如何接上 Dynamic APIRouter Builder，以及利用 FastAPI Lifespan 管理依序生長機制的處理手法。

4. **[04_Phase3_State_Evolution_And_Migration.md](./04_Phase3_State_Evolution_And_Migration.md)**
   > 專案中最具難度的技術挑戰 - 資料庫結構自動化同步策略。說明如何挾持 Alembic 的 MetaData 環境上下文並設計 Migration CLI 功能。核心概念：Safe-Mode 阻斷誤刪。

5. **[05_Phase4_Security_And_Advanced_Operations.md](./05_Phase4_Security_And_Advanced_Operations.md)**
   > 展現從 Prototype 進入企業實用層級的功能規劃。涵蓋魔法引數過濾系統 (`?age__gte=18`)、統一分頁標準，以及動態安插權限防護 (JWT Depends) 於生成路由之中。

6. **[06_Phase5_Production_Readiness.md](./06_Phase5_Production_Readiness.md)**
   > 戰備級維運規範考量。重點包含 Asyncpg 異步資料庫高併發連線池的引數配置原則、對抗 SQL Injection 分析的全局例外統一轉換 (如 500 error 轉為 409 Conflict) 及最後一步的 Docker/示例交付計畫。

---
*Created by System Analyst Architect.*
