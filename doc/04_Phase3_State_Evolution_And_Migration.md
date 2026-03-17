# Phase 3: 時間軸與狀態演進 (Database Migration Strategy)

若 Phase 1 & 2 是證明此概念可行的 PoC，那 Phase 3 就是決定這套 Meta-System 能不能實際上生產線 (Production Ready) 的核心。當 JSON 藍圖改變（如增加 `phone` 欄位），如果只是自動改 API，但 DB 沒跟上，立刻會引發崩潰。因此必須透過 Alembic 提供動態遷移 (Auto-Migration)。

## Task 3.1: 整合 Alembic 與環境設定 (Alembic Dynamic Config)

傳統開發中，Alembic 的 `env.py` 是去 import 我們寫死的 `models.py` 來取得 `Base.metadata`。但在 Meta-System 裡，Model 是程式啟動時憑空在記憶體裡長出來的。

### 3.1.1 攔截與重組 env.py 邏輯
必須在進入 Alembic context 之前，手動驅動 Phase 1 的邏輯先跑一次。

**策略設計：**
1. 在 `env.py` 中，呼叫 `SchemaParser().load_all()` 讀取藍圖。
2. 讓 `ORMFactory(Base)` 在記憶體中註冊所有的 sqlalchemy.Table。
3. 把載滿被動生成 Tables 的 `Base.metadata` 餵給 Alembic 配置。
```python
# alembic/env.py 摘錄設計
from core.factory import build_dynamic_models
from core.database import Base

# 動態加載藍圖以觸發 MetaData 產生
build_dynamic_models("./blueprints")

target_metadata = Base.metadata

def run_migrations_online():
    # 使用 Alembic 的 context 建構引擎
    # ...
```

## Task 3.2: 實作自動化遷移指令 (Auto-Migration CLI)

為降低維運門檻，設計一套單一入口的命令列工具，封裝複雜的 Alembic 指令，對一般開發者隱藏背後的 Autogenerate 邏輯。

### 3.2.1 CLI 組合指令設計
使用 `typer` 或 `click`：
```bash
python cli.py db status
python cli.py db makemigrations "Added _phone_ to users"
python cli.py db migrate
```

背後的執行邏輯 (Meta-Migration Flow)：
1. 觸發 `alembic revision --autogenerate -m "Message"`
2. Alembic 會比對 DB 內的 `alembic_version` 與實際 Table Schema，跟在 `target_metadata` 內（由 JSON 生出來）的結構差異。
3. 自動產出如同 `op.add_column(...)` 的修補腳本放入 versions 資料夾中。

### 3.2.2 降級防禦與「安全模式」 (Safe Mode Blueprint)

動態遷移的最高風險在於「修改欄位名稱」與「刪除欄位」。
傳統 Alembic 面對欄位重新命名時，常常會誤判為 `drop_column` + `add_column`，導致原始資料（如百萬筆用戶資料）瞬間全部遺失。

**安全防禦設計 (Safety Guard)：**
1. 在 Autogenerate 完成後，撰寫一個掛勾 (Hook) 掃描產生出來的 python migration script。
2. 若發現關鍵字 `op.drop_table` 或 `op.drop_column`：
    * **嚴格模式 (Strict)**: 阻斷遷移流程並拋出錯誤，要求開發者手動檢核/改寫腳本（比如改為 `op.alter_column`）。
    * **寬鬆模式 (Force)**: 若指明允許（例如指令加了 `--allow-destructive`），才予以放行。

這種防禦設計對於未來團隊協作與 CI/CD 自動部署（Continuous Deployment）時，是避免線上核心資料因 JSON 藍圖手誤而被抹除的最後一道防衛護城河。
