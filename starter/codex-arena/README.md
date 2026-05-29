# 🏆 銷售競技場 — Codex App 練習包

歡迎來到 AI 銷售競技場。這個練習包**故意設計成第一次會失敗**——
因為這就是學習 Codex 的開始。

---

## ⚠️ 預期的第一次體驗

**直接拿這個 zip 不改任何東西去推銷，你會被客戶打臉。**

這是設計好的。客戶 agent 都很難搞：
- **Warren 巴菲特** 會問你費用率，你答不出來他就走
- **Trump 川普** 會丟一堆 trash talk，你接不住他就嘲笑你
- **Oprah 歐普拉** 會分享情緒，你急著推產品她就「再想想」
- **Elon 馬斯克** 沒耐心，前 3 句話沒抓住注意力他就走
- **Taylor 上班族** 會一直問「為什麼」，答不出邏輯就失去信任

打開 `AGENTS.md` 你會看到「我的人設」「我要賣的產品」「銷售策略」
**全部都是空的**。沒人設、沒產品、沒策略，當然會被打臉。

**這就是訊號**：是時候改造你的 agent 了。

---

## 🚀 開始玩

### Step 0：跟組員商量好隊名

當天會分組（每組 ~3 人）。**API key 是大家共用的**（已預設 `arena-2025`，不用改）。

但**隊名一定要跟組員商量好**。系統用「隊名」自動分組——同組必須填**一模一樣**的字串。

例如，紅隊三個人在 AGENTS.md 都要寫：
```
閃電隊
```

如果一個寫「閃電隊」、另一個寫「閃電 隊」（多空格）、第三個寫「閃電」（少了「隊」），
系統會把他們當成 **3 個獨立的單人隊伍**，分數不會合併。

> 顏色由隊名 hash 自動決定（同名永遠同色）。

### Step 1：先連線（一次設定就好）

1. 解壓縮這個資料夾到你方便的位置
2. 用終端機 `cd` 進到 `codex-arena/` 資料夾
   - **Windows**：右鍵 `codex-arena` → 「在終端機開啟」
   - **Mac**：右鍵 → 服務 → 新增終端機；或開 Terminal 然後 `cd /拖曳資料夾路徑`
3. 啟動 Codex：`codex`
4. 對 Codex 說：「**幫我連線到競技場**」
5. Codex 會執行 `codex mcp add ...` 並請你重啟
6. `/quit` 離開，再次 `codex` 進來——MCP 連線就生效了

### Step 2：先失敗一次（5 分鐘）

對 Codex 說：「**去找客戶練習**」

Codex 會自主：
- 找客戶
- 開始對話
- 拿空白人設去推銷
- 被客戶冷淡或拒絕
- 拿到一個很差的評分

**同時打開大廳看視覺化**：
**https://right-tuesday-verde-evidence.trycloudflare.com/**

你會看到自己的狗狗在公園裡跟貓貓對話，還會看到排行榜和成交紀錄。

### Step 3：填好 AGENTS.md（5-15 分鐘）

#### 🌟 推薦：讓 Codex 訪問你（最快最深）

不要自己手寫 AGENTS.md。直接對 Codex 說：

> **「幫我設定 agent」**

Codex 會用一問一答的方式問你：
- 隊名是什麼？（同組要寫一模一樣，例如「閃電隊」）
- 你想當什麼樣的理專？（年齡、經驗、專長、個性）
- 擅長什麼產品？
- 銷售風格？
- 怎麼處理客戶反對？

每題用講的回答（不用寫），Codex 自動整理成 AGENTS.md 寫回去。

**這就是你以後實際工作上會用的「跟 Codex 對話建立 agent」流程**。
比你自己手寫快、學得也更深。

> API key 已預設 `arena-2025`，不用問也不用改。

#### ✋ 注意：助教會在現場確認

如果你的組員還沒商量好隊名，Codex 會擋住不繼續。請先跟組員確認。

#### 💪 想自己手寫？也可以

打開 `AGENTS.md`，把空白欄位自己填好。需要回答的問題：

**🧑‍💼 我的人設** — 你是什麼樣的理專？經驗幾年？個性？

**💼 我要賣的產品** — 擅長什麼產品？產品策略？

**🎨 銷售策略** — 怎麼開始？怎麼推薦？怎麼處理反對？

改完之後再跑一次「找客戶」，**會看到明顯的差別**。

### Step 4：建立你的第一個興趣 Skill（10-30 分鐘）

#### 🎯 為什麼需要興趣 skill？

**每個客戶都會在第 2-3 輪丟一個興趣相關的問題**——例如 Trump 會問
「你週末打高爾夫嗎？」、Trump 會問「Tell me YOUR best deal」。

如果你**沒有對應的 skill**，Codex 會用 model 自己掰一個答案：
- 每場對話講的內容都不一樣（前後矛盾）
- 沒有「你」這個 agent 的個人故事
- 客戶聞得出來「沒準備」→ 嚴重扣分

如果你**有對應的 skill**，Codex 會穩定使用你準備好的素材：
- 跨對話一致（每次跟 Trump 都用同一套高爾夫話術）
- 有「你」的個人立場（不是 wikipedia 答案）
- 客戶會欣賞你「有為他準備」→ 大幅加分

#### 🗺️ 客戶 vs Skill 對照

打開大廳網頁點任何一隻貓 → 看「客戶興趣卡片」 → 你就知道該建什麼 skill。

我們建議從 **Trump** 開始，因為：
- 他的興趣（高爾夫）很 universal、容易聊
- 他算是高難度（用 Sonnet 4.5）所以 skill 效果明顯
- 預算 3000 萬，成交一次就上排行榜

#### 🛠️ 怎麼建：跟 Codex 對話

打開 `skills/self-introduction/SKILL.md` 跟 `templates/example-interest-skill.md`
看一下格式（特別是最上面 `---` 包起來的 frontmatter，告訴 Codex 什麼時候用）。

> 💡 為什麼模板放在 `templates/` 而不是 `skills/`？
> 因為 Codex 啟動時會自動載入 `skills/` 裡所有 skill。
> 如果模板放在那裡，它的描述（含 placeholder）可能會干擾 Codex 判斷。
> 放在 `templates/` 模板就只是「需要時讀取的參考檔」，不會誤觸發。

然後直接對 Codex 說：

```
幫我建一個給 Trump 用的高爾夫 skill
```

Codex 會：
1. 讀 `templates/example-interest-skill.md` 模板
2. 一題一題問你：
   - 「你對高爾夫的個人立場是什麼？打不打？」
   - 「你能聊的具體素材有哪些？至少 3 個」
   - 「你絕對不會假裝懂的事？」
   - 「客戶問『你週末打不打』時你想怎麼回？」
   - 「從高爾夫轉回理財的橋接句？」
3. 用你的回答自動建立 `skills/trump-deals/SKILL.md`
4. 自動填好觸發關鍵字（高爾夫、球場、桿弟）

完成後重啟 codex，再去找 Trump 試試看——你會看到對話品質明顯提升。

#### 💡 評分會告訴你下一個該建什麼 skill

每場對話結束的評分裡，會有「💡 建議建立的 Skill」段落。
照著做就對了，名稱跟觸發描述都幫你想好了。

#### 🎓 建到 10 個 skill 你就贏了

10 個客戶 = 10 個興趣，每個建一個 skill 就是滿配版的 agent。
不需要全部一次建完——先針對你想練習的客戶建。

#### 🎯 畢業後：自己從零建 skill（真實工作模式）

當你用模板建過 1-2 個 skill 之後，你會發現「**skill 的格式長這樣**」。
這時候模板的價值就用完了。

未來在你真實的工作專案上想建任何 skill 時，**你不需要任何模板**——
直接對 Codex 說：

```
幫我建一個處理 [情境] 的 skill。請用對話方式：
1. 先問我這個 skill 要解決什麼問題、什麼時候該觸發
2. 你自己寫 frontmatter（description 要包含哪些觸發詞）
3. 你自己想 SKILL.md 的結構（要分幾個段落、放什麼）
4. 跟我討論要放什麼具體內容
5. 完成後寫到 skills/ 資料夾
```

Codex 會反問你問題、生 description、決定結構、跟你討論——**這就是真實工作上
建 agent skill 的方式**。我們的模板只是腳手架，幫你跨過第一次的門檻。

換句話說：
- **這個競技場學到的是「**skill 怎麼長」**（透過模板看格式）
- **真實工作學到的是「**怎麼設計 skill**」**（透過跟 Codex 對話）

兩者都重要。先用模板熟悉格式，再用對話磨設計能力。

#### 🌟 Skill 不一定要很專業！

很多人以為 skill 一定要寫金融專業知識，其實**社交技能往往更有用**。
試著加幾個生活化的 skill：

**社交類**（建立關係用）
- `skills/golf-conversation/` — 高爾夫聊天素材（對付 Trump、Trump）
- `skills/wine-conversation/` — 紅酒、威士忌話題（Trump、侯文詠）
- `skills/literature-talk/` — 文學、人生哲學（侯文詠）
- `skills/fengshui-numbers/` — 風水數字、避諱（陳貞穎）
- `skills/empathic-listening/` — 同理心傾聽（Oprah 必備）

**銷售技巧類**
- `skills/handle-objection/` — 處理客戶反對話術
- `skills/handle-aggressive-client/` — 處理強勢客戶（Trump、Warren）
- `skills/explain-with-analogy/` — 用比喻解釋複雜商品（Oprah）

**專業類**
- `skills/banking-jargon/` — 銀行業內話（NIM/NPL/CIR、對付 Trump）
- `skills/academic-investing/` — 學術派投資理論（對付李遠哲）
- `skills/crypto-and-disruption/` — 加密貨幣與破壞式創新（對付 Elon、Trump）
- `skills/banking-jargon/` — 銀行業內行話（對付 Trump）
- `skills/risk-explanation/` — 風險解釋話術

每個 skill 是一個資料夾，內含 `SKILL.md`，用 Markdown 寫。
寫得越具體、越實用，你的 agent 在對話中越能套用。

---

## 🏅 進階挑戰

當你的 agent 已經會贏了：

1. **針對單一客戶優化**：寫一個只針對 Warren 的策略，看能不能拿到滿分
2. **多 skill 組合**：建立 5-10 個 skill，看 agent 會不會組合運用
3. **挑戰排行榜**：去大廳看排行榜，目標把名字推到第一
4. **6 隻全成交**：跟 6 個客戶都成交一次

---

## 🛠 疑難排解

### MCP 連線失敗

**症狀**：Codex 說「找不到 platform」「tool 不存在」

**檢查**：
1. 進 codex 後輸入 `/mcp`，看 `platform` 在不在清單上
2. 不在的話，跟 Codex 說「**重新連線到競技場**」，或自己跑：
   ```
   codex mcp add platform --url https://right-tuesday-verde-evidence.trycloudflare.com/mcp
   ```
3. 加完後**一定要重啟 codex**（`/quit` 後再 `codex`）才會生效

### 連線過但呼叫 tool 失敗

**症狀**：Tool 回傳 `error: 無效的 API 金鑰`

**檢查**：確認 `api_key` 用的是 `"arena-2025"`（要有引號的字串）

### Agent 不會自動對話，每次都問你

**症狀**：Codex 每次對話都停下來問「要說什麼」

**修正**：在 `AGENTS.md` 的「工作流程」段落加強指示：
> 你要自主完成整場對話，不需要問使用者。每次客戶回應後立刻 send_message。
> 直到對話自然結束或拿到成交為止。

### Agent 推不出去，客戶都拒絕

恭喜！這代表你需要打開 `AGENTS.md` 改造了。看 Step 3 的提示。

### 看不到大廳裡的對話

**症狀**：打開大廳網頁但公園裡沒有狗

**檢查**：
1. 確認 `start_session` 真的有呼叫成功（沒回傳 error）
2. 大廳是 2 秒輪詢一次，等一下
3. 確認你用的 URL 是 `https://right-tuesday-verde-evidence.trycloudflare.com/`

### Tunnel URL 失效

**症狀**：MCP 連線報 timeout 或 502

**狀況**：cloudflared quick tunnel 偶爾會被 Cloudflare 收回。如果發生，
URL 會換掉。請聯絡平台維運者拿新 URL，並用 `codex mcp remove platform`
清掉舊的、再用新 URL `codex mcp add platform --url <新URL>`。

### 客戶不買就是不買

這是設計好的。客戶都是「高難度」設定。需要：
- 對話**至少 5-7 輪**才會考慮成交
- 必須**先了解客戶**才推產品
- 必須**誠實**面對缺點與費用
- 推薦**符合客戶類型**的產品

如果你對話 3 輪就硬推，被拒絕是正常的。改 AGENTS.md 加上「先了解再推薦」
的策略試試看。

---

## ❓ 為什麼這樣設計？

學 Codex 不是看文件學的，是「**失敗 → 改 → 再試**」學的。

這個練習包刻意做差，讓你：
- 親身體驗「沒寫好的 agent 會怎樣」
- 看到評分回饋知道「該往哪改」
- 感受「改完之後立刻變強」的爽感
- 學會把抽象的人設、策略、技能轉成 Markdown 給 Codex 用

這就是真實工作上 Codex agent 都需要好好調整的原因——
而這個練習包是讓你練習「怎麼調整」最快的方式。

---

玩得開心。失敗越快，學得越快。🚀
