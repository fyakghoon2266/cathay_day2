# 🏆 AI 銷售競技場 — 專案總結

## 一、專案目的

這是一個讓**初學者透過實戰學會配置 Codex agent** 的競賽平台。

學習目標排序：

1. **怎麼寫 AGENTS.md**（agent 人設、行為定義）
2. **怎麼建立 SKILL**（透過跟 Codex 對話建立）
3. **MCP 連線概念**（外部服務如何接入 Codex）

「銷售」只是場景包裝。重點是「練習 Codex 工程」。

---

## 二、玩法概述

```
使用者下載 zip → 解壓 → 跟 Codex 對話設定 agent → 進入競技場找客戶賣產品
```

10 位 AI 客戶坐在公園裡（每隻是隻貓 🐱），各有不同個性、興趣、預算。
參賽者的 agent 是一隻狗 🐶 進公園找客戶推銷，**目標是賣最多錢上排行榜**。

每場對話結束會有 AI 教練評分 + 建議「下次該建什麼 skill」。

---

## 三、專案組成

### A. Server 端（在這台 EC2 上）

```
codex-server/
├── server.py                    ← FastMCP server（提供 tools 給 Codex）
├── personas.yaml                ← 10 位客戶設定
├── api_keys.yaml                ← 共用一把 arena-2025
├── src/
│   ├── customer_agent.py        ← 客戶 LLM 邏輯（Bedrock 呼叫）
│   ├── salesperson_agent.py     ← run_full_session 自動演示用
│   ├── session_manager.py       ← Redis session 管理
│   ├── arena.py                 ← 預算/成交/排行榜邏輯
│   └── ...
├── static/index.html            ← 大廳網頁（公園視覺化）
└── starter/
    ├── codex-arena.zip          ← 給使用者下載的練習包
    └── codex-arena.tar.gz
```

**運作組件**：

- **AWS Bedrock**：客戶 LLM 用 Sonnet 4.5（Trump/Daniel/Elon）或 Haiku 4.5（其他）
- **Redis**（docker container）：session、預算、排行榜
- **Cloudflared tunnel**：對外提供 HTTPS URL 給 Codex 連線
- **FastMCP**：標準 MCP server，提供 5 個 tools

### B. 對外服務 URL

```
MCP server：    https://right-tuesday-verde-evidence.trycloudflare.com/mcp
大廳網頁：      https://right-tuesday-verde-evidence.trycloudflare.com/
下載 zip：      https://right-tuesday-verde-evidence.trycloudflare.com/download/codex-arena.zip
下載 tar.gz：   https://right-tuesday-verde-evidence.trycloudflare.com/download/codex-arena.tar.gz
```

### C. 使用者拿到的 starter pack

```
codex-arena/
├── AGENTS.md                                ← 帶 onboarding 流程指令
├── README.md                                ← 學習路徑說明
├── skills/
│   └── self-introduction/SKILL.md           ← 唯一的真 skill
└── templates/
    └── example-interest-skill.md            ← 興趣 skill 模板
```

---

## 四、10 位客戶介紹

| 客戶 | 對應人物 | 主興趣 | 難度 | 預算 |
|---|---|---|---|---|
| Warren | 巴菲特 | 低成本指數投資 / Bogle | 高 | 3,000萬 |
| Elon | 馬斯克 | 比特幣 / 加密貨幣 | 高 ⭐ | 1,500萬 |
| Trump | 川普 | 地產 deal-making | 高 ⭐ | 5,000萬 |
| Lee | 李遠哲（諾貝爾） | 學術投資理論 | 高 | 1,500萬 |
| Daniel | **鄧崇儀**（國泰世華總經理） | 高爾夫 | 高 ⭐ | 3,000萬 |
| Oprah | 歐普拉 | 心靈成長 | 一般 | 1,000萬 |
| Taylor | Taylor Swift（風格） | 買房規劃 | 一般 | 300萬 |
| Hou | 侯文詠 | 文學 | 高 | 2,000萬 |
| Rikko | 理科太太 | 創作者經濟 | 高 | 800萬 |
| Chen | 陳貞穎（吳寶春店共創人） | 風水數字 | 一般 | 4,000萬 |

⭐ 這三個用 Sonnet 4.5（更聰明難搞），其他用 Haiku 4.5

**總預算**：2.21 億 — 所有人加總賣出的金額上限

---

## 五、5 個核心 MCP Tools

| Tool | 用途 |
|---|---|
| `list_customers` | 列出所有客戶（含剩餘預算、興趣） |
| `find_customer` | 隨機/偏好分配一位客戶 |
| `start_session` | 開始一場對話 |
| `send_message` | 跟客戶對話一輪 |
| `end_session` | 結束 + 拿 AI 教練評分 |

---

## 六、競賽機制

### 1. 分組

- 不分組就一個人一隊也行
- 同組必須 AGENTS.md 寫**一模一樣的隊名**才會合併分數
- 顏色由隊名 hash 自動配（同名同色，10 色 palette）

### 2. 排行榜

- **個人榜**：累積成交金額
- **團隊榜**：同隊成員加總

### 3. 成交機制

- 客戶 LLM 自己決定買不買
- 在回應第一行寫 `[成交:產品名:金額]` 才算數
- 預算先到先扣（race condition 已知，demo 規模不會撞）

### 4. 防護機制

- 客戶有「成交門檻」prompt（至少幾輪、必須做到 X）
- 每場隨機 mood 池（**規劃中，還沒實作**）
- **自動收尾機制**（已實作）：
  - 1-4 輪：正常對話
  - 5-6 輪：客戶開始暗示要結束
  - 7-8 輪：必須表態
  - 9+ 輪：強制結束
- 高難度客戶閒聊接不住會嚴重扣分

---

## 七、Skill 觸發機制（這個專案最巧妙的地方）

### 客戶會「強制」說興趣關鍵字

每個客戶在第 2-3 輪會強制說一句含特定關鍵字的話：

- Daniel：「你週末打**高爾夫**嗎？」
- Trump：「Tell me about YOUR best **deal**」
- 侯文詠：「你最近**讀什麼書**？」

### 使用者建 skill 後就會被自動觸發

若使用者建了 `daniel-golf/SKILL.md`，description 寫「客戶提到高爾夫時使用」，
Codex 看到客戶說高爾夫 → 自動讀這個 skill → 對話品質大幅提升 → 加分。

### 模板放在 `templates/` 不會誤觸發

模板有 `[REPLACE_客戶名]` 等 placeholder，**不會被 Codex 自動載入為 skill**，
但「幫我建 daniel-golf」時 Codex 會去讀它當參考。

---

## 八、學習路徑（給使用者體驗）

```
Step 0 → 跟組員商量隊名（API key 已預設 arena-2025）
Step 1 → cd codex-arena && codex
Step 2 → 對 Codex 說「幫我連線到競技場」
Step 3 → 重啟 codex 後說「幫我設定 agent」
        ↓ Codex 一問一答填好 AGENTS.md
Step 4 → 對 Codex 說「去找客戶練習」
        ↓ Codex 自主完成對話
Step 5 → 看評分 → 評分建議「請建 daniel-golf skill」
Step 6 → 對 Codex 說「幫我建一個給 Daniel 用的高爾夫 skill」
        ↓ Codex 一問一答幫你填模板，自動建出 SKILL.md
Step 7 → 重啟 codex → 再找 Daniel → 看到對話品質明顯提升 → 成交
Step 8 → 重複 Step 5-7 為其他客戶各建一個興趣 skill
```

---

## 九、UI / 大廳

公園畫面（即時更新）：

- 🐱 10 隻貓固定位置 + 待機時會慢慢漫步、頭上冒待機台詞
- 🐶 狗從公園底部走進來找對應的貓
- 💬 對話泡泡（黃 = 理專、藍 = 客戶）
- 🎉 成交特效
- 點任何貓 → 顯示客戶興趣卡片 + 該客戶所有對話列表
- 點狗 → 顯示那場對話內容
- 上方儀表板：10 個客戶剩餘預算（顏色條 + 「剩餘 / 原本」）
- 側邊：團隊榜 + 個人榜 + 最近成交

---

## 十、技術亮點（給工程觀眾看的）

| 設計 | 用意 |
|---|---|
| **MCP Streamable HTTP** | 跨 firewall、單一 HTTPS endpoint |
| **多模型混搭** | Haiku 跑量、Sonnet 跑硬骨頭、控成本 |
| **per-customer model_id** | yaml 配置每個 persona 用哪個模型 |
| **強制觸發句設計** | 解決 LLM-as-judge 不可預測的觸發問題 |
| **隊名 hash → ID + Color** | 不需要中央發 key，使用者自己組隊 |
| **轉錄存檔** | 每場對話結束存 JSON，可離線分析評分 |
| **Cloudflared tunnel** | demo 用，不需要 buy domain |

---

## 十一、明天 demo 建議的展示流程

1. **打開大廳網頁** — 看公園、貓在漫步、頭上有待機台詞
2. **show 一個範例對話**（你或助教先跑一場）— 讓觀眾看狗走進來、對話泡泡、成交特效
3. **講解 starter pack 結構** — AGENTS.md / templates / skills
4. **show 用 Codex 建 skill** — 跟 Codex 對話，幾分鐘建出 daniel-golf
5. **重啟後再跑一場** — 看 skill 觸發、對話品質提升、成交
6. **看排行榜更新**

預估 demo 時間 15-20 分鐘。

---

## 十二、目前已知限制 / 待改進

- 預算扣款有 race condition（demo 規模不會撞，可暫不修）
- Cloudflared quick tunnel 偶爾會被收回 → 換 named tunnel 才能長期穩定
- 剛才討論到的 mood 系統還沒做（demo 不需要也行）
- 對話速度：8 分鐘 → 已用「自動收尾」減到 3-5 分鐘
