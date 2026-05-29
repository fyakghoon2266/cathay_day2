# AI Sales Arena — Codex App Training Platform

AI 銷售競技場是一個讓 Codex CLI 使用者練習配置 agent 的實戰平台。使用者透過 MCP 連線，讓自己的 Codex agent（理專）與平台上的客戶 agent（由 LLM 驅動）進行多輪銷售對話。平台提供即時視覺化大廳、團隊/個人排行榜、AI 教練評分，並引導使用者學習 `AGENTS.md` 與 `skills/` 的配置方式。

## 核心概念

```
使用者的 Codex App（理專 agent）
    ↕ MCP (Streamable HTTP)
本平台 Server（客戶 agent + 評分 + 排行榜）
    ↕
即時網頁大廳（公園視覺化）
```

- **客戶 agent**：10 位名人個性的客戶（巴菲特、川普、李遠哲等），由 Bedrock Claude 模型驅動
- **理專 agent**：使用者的 Codex CLI，透過 MCP tools 與客戶對話
- **學習目標**：讓使用者學會配置 `AGENTS.md`（人設）和建立 `skills/`（技能），而不是只學銷售

## 技術架構

```
┌─ Codex CLI (使用者電腦) ─────────┐
│  AGENTS.md + skills/              │
│  透過 MCP 呼叫 platform tools    │
└───────────────────────────────────┘
            ↕ HTTPS (Cloudflared Tunnel)
┌─ Server (AWS EC2) ───────────────┐
│  FastAPI + FastMCP                │
│  Bedrock (Haiku 4.5 / Sonnet 4.5)│
│  Redis (session + leaderboard)    │
│  Static dashboard (HTML/JS)       │
└───────────────────────────────────┘
```

## 專案目錄結構

```
codex-server/
├── server.py                 # 主程式入口：MCP server + Web API + 靜態頁面路由
├── personas.yaml             # 10 位客戶的完整人設定義（個性、興趣、成交條件、觸發句）
├── api_keys.yaml             # API key 設定（共用 key + 管理員 key）
├── requirements.txt          # Python 依賴
├── docker-compose.yml        # Redis 容器定義
│
├── src/                      # Server 核心邏輯模組
│   ├── __init__.py
│   ├── config.py             # 環境變數與常數（AWS region、model ID、Redis URL、TTL）
│   ├── auth.py               # API key 驗證（讀 api_keys.yaml）
│   ├── customer_agent.py     # 客戶 LLM 呼叫（system prompt 組裝、成交格式、閒聊觸發、收尾機制）
│   ├── salesperson_agent.py  # 理專 LLM 呼叫（run_full_session 自動模式用）
│   ├── session_manager.py    # Redis session CRUD（建立、讀取、加輪、結束、TTL 管理）
│   ├── personas_loader.py    # 載入 personas.yaml、提供查詢 API
│   ├── arena.py              # 競技場邏輯（預算管理、成交偵測 regex、排行榜、團隊記錄）
│   └── transcript.py         # 對話結束時存檔為 JSON transcript
│
├── static/
│   └── index.html            # 即時大廳網頁（公園視覺化、排行榜、對話框、預算儀表板）
│
├── starter/                  # 給使用者下載的 Starter Pack
│   ├── codex-arena.zip       # 打包好的 zip（Windows）
│   ├── codex-arena.tar.gz    # 打包好的 tar.gz（Mac/Linux）
│   └── codex-arena/          # Starter Pack 原始檔案
│       ├── AGENTS.md         # 使用者的 agent 設定（含 onboarding 流程指令）
│       ├── README.md         # 使用者面向的學習指南
│       ├── skills/
│       │   └── self-introduction/SKILL.md   # 範例 skill（自我介紹）
│       └── templates/
│           └── example-interest-skill.md    # 興趣 skill 建立模板
│
├── transcripts/              # 對話歷史 JSON 存檔（gitignore）
├── test_mcp_server.py        # 早期測試用的簡易 MCP server
└── .gitignore
```

## 各模組詳細說明

### `server.py`

主程式。整合所有功能：

- **MCP Tools**（給 Codex agent 呼叫）：
  - `list_customers` — 列出 10 位客戶（含預算、難度、興趣）
  - `find_customer` — 隨機/偏好配對客戶
  - `start_session` — 建立對話 session
  - `send_message` — 發送訊息並取得客戶回應（含成交偵測）
  - `end_session` — 結束對話並取得 AI 教練評分
  - `run_full_session` — 全自動 demo 模式（server 自己跑雙方）

- **Web API**（給前端大廳用）：
  - `GET /` — 公園大廳頁面
  - `GET /api/sessions` — 所有 session 即時狀態
  - `GET /api/leaderboard` — 個人排行榜
  - `GET /api/team_leaderboard` — 團隊排行榜
  - `GET /api/deals` — 最近成交紀錄
  - `GET /api/customers` — 客戶列表（含預算、興趣）
  - `GET /download/codex-arena.zip` — Starter Pack 下載

### `src/customer_agent.py`

客戶 LLM 的核心：

- **System prompt 組裝**：動態注入人設、興趣觸發句、閒聊扣分規則、收尾壓力機制
- **收尾機制**：根據輪數（1-4 正常 / 5-6 暗示結束 / 7-8 必須表態 / 9+ 強制結束）
- **成交格式**：強制第一行寫 `[成交:產品名:金額]`，避免被 max_tokens 截斷
- **評分系統**：結束後由 Sonnet 4.5 做教練評分，明確建議該建哪些 skill
- **Per-customer 模型**：高難度客戶（Trump/Elon）用 Sonnet 4.5，其他用 Haiku 4.5

### `src/arena.py`

競技場核心邏輯：

- **預算池**：每個客戶有初始預算，成交時扣款
- **成交偵測**：Regex 解析 `[成交:產品名:金額]`（支援截斷版本、全形冒號、逗號金額）
- **排行榜**：Redis sorted set，支援個人 + 團隊
- **團隊管理**：依 `team_display_name` 自動分組，hash 配色

### `src/session_manager.py`

Redis session 管理：

- 每個 session 存為 JSON（含 history、customer_id、agent_name、team 資訊）
- TTL 3 小時自動過期
- 支援 add_turn、end_session、turn limit 檢查

### `personas.yaml`

10 位客戶的完整定義：

| ID | 名稱 | 難度 | 模型 | 預算 |
|---|---|---|---|---|
| warren | 巴菲特 | hard | Haiku 4.5 | $3,000萬 |
| elon | 馬斯克 | medium | Sonnet 4.5 | $1,500萬 |
| oprah | 歐普拉 | easy | Haiku 4.5 | $1,000萬 |
| taylor | 上班族 | easy | Haiku 4.5 | $300萬 |
| trump | 川普 | hard | Sonnet 4.5 | $5,000萬 |
| lee | 李遠哲 | hard | Haiku 4.5 | $1,500萬 |
| rikko | 理科太太 | medium | Haiku 4.5 | $800萬 |
| hou | 侯文詠 | medium | Haiku 4.5 | $2,000萬 |
| chen | 陳貞穎 | medium | Haiku 4.5 | $4,000萬 |

每位客戶包含：人設 prompt、購買決策條件、開場白、待機台詞、興趣列表、強制觸發句、閒聊難度。

### `static/index.html`

即時大廳網頁（單檔 SPA）：

- **公園視覺化**：10 隻貓（客戶）漫步 + 狗（理專）走入對話
- **預算儀表板**：10 個卡片顯示「剩餘/原始」預算 + 進度條
- **團隊 + 個人排行榜**：即時更新
- **對話框**：點擊貓/狗查看完整對話歷史
- **興趣卡片**：點擊客戶顯示興趣 + 難度
- **每 2 秒自動 polling** 刷新所有數據

### `starter/codex-arena/`

給使用者的 Starter Pack：

- **AGENTS.md**：含 onboarding 指令（Codex 一問一答填人設）+ 工作流程 + 客戶快速指南 + 建 skill 流程
- **README.md**：學習路徑（失敗 → 改 agent → 建 skill → 上排行榜）
- **skills/self-introduction/**：通用範例 skill（永遠有效）
- **templates/example-interest-skill.md**：興趣 skill 模板（不在 skills/ 避免誤觸發）

## 快速啟動（開發者）

### Prerequisites

- Python 3.11+
- Docker（用來跑 Redis）
- AWS credentials（有 Bedrock Claude 模型的存取權限，us-west-2）

### 啟動

```bash
# 1. 安裝依賴
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. 啟動 Redis
docker run -d --name codex-redis -p 6379:6379 redis:7-alpine

# 3. 啟動 server
.venv/bin/python server.py
# Server 會跑在 http://0.0.0.0:8765

# 4.（可選）開 tunnel 讓外面連
cloudflared tunnel --url http://127.0.0.1:8765 --no-autoupdate
```

### 環境變數

參考 `src/config.py`：

| 變數 | 預設 | 說明 |
|---|---|---|
| `AWS_REGION` | us-west-2 | Bedrock region |
| `REDIS_URL` | redis://localhost:6379 | Redis 連線 |
| `MCP_PORT` | 8765 | Server port |
| `SESSION_TTL_HOURS` | 3 | Session 過期時間 |
| `MAX_TURNS` | 50 | 單場對話最大輪數 |

### 重置競技場

```bash
docker exec codex-redis redis-cli FLUSHDB
# 然後重啟 server（重新初始化預算）
```

## 使用者流程

1. 下載 starter pack（`/download/codex-arena.zip`）
2. 解壓 → `cd codex-arena/` → `codex`
3. 「幫我連線到競技場」→ 重啟 codex
4. 「幫我設定 agent」→ 一問一答填 AGENTS.md
5. 「去找客戶練習」→ 自主對話 → 看評分
6. 「幫我建一個給 Trump 用的地產 deal skill」→ 建 skill → 重啟 → 再試
7. 打開大廳看排行榜

## 授權

Internal use only.
