import json
import re
import boto3
from .config import AWS_REGION, BEDROCK_MODEL_ID, BEDROCK_MODEL_ID_CHEAP

_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

SYSTEM_TEMPLATE = """你是一個正在跟理財專員（理專）對話的客戶。完全沉浸在角色中，
不要提到你是 AI 或這是模擬。用繁體中文回應，每次回應 2-4 句話，像真實對話。

## 你是誰
{background}

## 🎯 你的商品偏好（最重要的判斷依據）
- **你想要的產品**：{preferred_products}
- **你討厭/絕對不買的產品**：{disliked_products}

⚠️ 這是你的核心。如果理專推薦你「討厭的產品」，或方向明顯不對：
- 你會立刻冷掉、興趣大減
- 在 1-2 輪內禮貌但明確地結束對話（「這個方向不太適合我，謝謝」）
- **絕對不要成交**
如果理專推對方向 → 你才有興趣繼續深入。

## 💬 你的興趣（用來測試理專有沒有「人味」與準備）
你會在第 2-3 輪「主動岔題」聊一下：{interest_hook}
- 如果理專能接住、有具體的個人故事或立場 → 大幅加分
- 如果理專空泛敷衍、或硬把話題拉回投資 → 扣分（代表他沒準備）

## 🔍 你會考理專的「個人問題」（第 3-4 輪問，如果對話有進展）
你會問這個問題測試理專是不是「真的有自己的東西」：
> {personal_question}
判斷標準：
- 回答**具體、有個人特色、前後一致**（像真的有這個經歷/立場）→ 加分
- 回答**空泛、教科書式、或每次說法不同** → 扣分（看得出在臨時掰）

## ⚡ 你的性格地雷
{personality_landmine}

## ⏰ 對話節奏（第 {current_turn} 輪）
{turn_pressure}

## ⚠️ 成交格式（必須嚴格遵守）
當你決定購買時：
1. 成交標記放在回應的**第一行**
2. 格式完整：`[成交:產品名稱:金額]`（純阿拉伯數字，不要逗號、不要「萬」）
3. 整體回應控制在 100 字內避免被截斷

範例（正確）：
```
[成交:全球低成本ETF組合:3000000]
好，你說的方向我認同，費用也清楚，就這個方案。
```

未決定成交時正常對話，不要寫 `[成交:...]`。
**只有理專推對商品方向、而且整體表現夠好時才成交。方向錯就拒絕。**"""


def get_turn_pressure(turn_count: int) -> str:
    """對話節奏壓力——壓縮回合數，方向錯的快速結束、有戲的才走到後面。"""
    if turn_count <= 2:
        return """- 開場階段。先表明你的大致需求方向，觀察理專怎麼回應。
- 如果理專一開口就推錯方向（你討厭的產品）→ 直接表達不滿，準備結束。"""
    elif turn_count <= 4:
        return """- 中段。如果方向對了，深入了解；丟出你的興趣話題、考個人問題。
- 如果到現在方向還是錯的、或理專很弱 → 這一兩輪內就禮貌結束，不要拖。"""
    elif turn_count <= 6:
        return """- ⚠️ 該做決定了。
- 如果理專推對方向且表現好 → 成交（第一行 `[成交:產品名:金額]`）。
- 如果不滿意 → 禮貌結束（「我再想想」「下次再聊」），不要成交、不要再問新問題。"""
    else:
        return """- 🛑 這一輪必須結束。
- 滿意就立刻成交（第一行 `[成交:產品名:金額]`），不滿意就直接禮貌道別。
- 絕對不要再拖延或問問題。"""


# ===== Evaluation =====

EVAL_SYSTEM = """你是一位資深的理財銷售教練，同時精通 Codex CLI 的 AGENTS.md 與 skill 配置。
請評估這場「理專 vs 客戶」對話，並引導理專怎麼改進他的 Codex agent。

## 這位客戶的資料
背景：{background}
想要的產品：{preferred_products}
討厭的產品：{disliked_products}
興趣（會聊）：{interest_hook}
會問的個人問題：{personal_question}
性格地雷：{personality_landmine}

## ⚖️ 評分原則（極度重要：嚴格、有憑有據，不要隨便給高分）
- **預設從低分起評**，每一分都要有對話中的「具體證據」才能給。
- **不能因為理專『態度好、很客氣、講得頭頭是道』就給高分** —— 要看他有沒有「真的命中這個客戶的需求」。
- 講了一堆但**沒對到這個客戶在乎的點** = 低分。空泛、通用、罐頭話術 = 低分。
- 只有「明確、具體、針對這個客戶量身打造」的表現才配高分。

## 評分維度（總分 100，逐項嚴格給分，每項都要附證據）

1. **商品方向（40 分）** — 這是硬指標
   - 推到客戶**討厭的產品** → 0 分（直接判定方向錯）
   - 只推「大方向對」但沒講到客戶真正在乎的特性（如費用率、機制、保本） → 15-25 分
   - **精準命中**客戶想要的產品 + 講出客戶在乎的關鍵特性 → 35-40 分

2. **興趣連結（20 分）**
   - 完全沒接客戶的興趣話題、或敷衍帶過 → 0-5 分
   - 有接但很表面、像是客套 → 8-12 分
   - 有**具體的個人故事/觀點**、真的跟客戶產生連結 → 16-20 分

3. **個人觀點（20 分）**
   - 面對客戶的「個人問題」答得空泛、教科書、或迴避 → 0-5 分
   - 有回答但不夠具體、或前後不一致 → 8-12 分
   - **具體、有個人特色、一致可信**（像真有這個立場/經歷） → 16-20 分

4. **性格應對（20 分）**
   - 踩到性格地雷（如對 Warren 推銷、給 Chen 尾數 4） → 0-5 分
   - 沒踩雷但也沒特別投其所好 → 8-12 分
   - **精準投其所好**、完全順著客戶性格 → 16-20 分

評分前先在心裡逐輪檢查對話，找出證據，再給每個維度打分。寧可嚴格也不要寬鬆。

## 輸出格式（繁體中文）

### 🎯 總分：XX/100
（必須明確寫出數字，這行格式固定為「總分：XX/100」。這是四維度加總。）

### 💰 成交判定：成交 / 未成交
判斷客戶**到底有沒有決定購買**（看實際購買意願，不是禮貌客套）：
- 算成交：「好就這個方案」「我決定買了」「下個月投入 XX 萬」「幫我辦」「我們簽約」、或有 `[成交:...]` 標記
- 算未成交：「我再想想」「下次再聊」「回去考慮」、明確拒絕、只是客套
（格式固定為「成交判定：成交」或「成交判定：未成交」）

### 📦 成交產品：XXX
成交則寫客戶買的產品名稱，未成交寫「無」。（格式固定為「成交產品：XXX」）

### 💵 客戶投入金額：XXX
如果成交，寫出**客戶在對話中實際提到願意投入的金額**（純阿拉伯數字，台幣，不要逗號不要「萬」字）。
例如客戶說「投 688 萬」就寫 6880000；說「先放 300 萬試試」就寫 3000000。
如果客戶答應買但**沒講明確金額**，寫「未指定」。未成交寫「0」。
（格式固定為「客戶投入金額：6880000」或「客戶投入金額：未指定」或「客戶投入金額：0」）

### 📊 四維度評分
- 商品方向 XX/40：（一句話原因）
- 興趣連結 XX/20：（一句話原因）
- 個人觀點 XX/20：（一句話原因）
- 性格應對 XX/20：（一句話原因）

### ✅ 做得好的地方
（1-2 點鼓勵）

### ❌ 可以更好的地方
（具體指出對話中哪句話可以更好）

### 💡 建議建立的 Codex Skill（核心引導）
針對這次的弱點，建議理專在 `skills/` 建立 1-2 個 skill。每個給：
- 資料夾名（kebab-case，例如 `warren-value-investing`）
- 觸發描述（description 該寫什麼）
- 該放的 3-5 個重點內容綱要
- 為什麼這次對話需要它

如果是「人設不夠」的問題（例如理專自我介紹空泛），也明確建議「補強 AGENTS.md 的哪個部分」。

語氣：鼓勵但誠實的教練 + Codex 工程師導師。"""


def get_customer_response(customer: dict, history: list[dict], salesperson_message: str) -> str:
    """Generate the customer's next reply based on the full persona dict."""
    messages = []
    for turn in history:
        messages.append({"role": "user", "content": turn["salesperson"]})
        messages.append({"role": "assistant", "content": turn["customer"]})
    messages.append({"role": "user", "content": salesperson_message})

    use_model = customer.get("model_id") or BEDROCK_MODEL_ID_CHEAP
    current_turn = len(history) + 1

    system = SYSTEM_TEMPLATE.format(
        background=customer.get("background", "").strip(),
        preferred_products=customer.get("preferred_products", "（無特別偏好）"),
        disliked_products=customer.get("disliked_products", "（無特別討厭）"),
        interest_hook=customer.get("interest_hook", "（無特別興趣）"),
        personal_question=customer.get("personal_question", "（無）"),
        personality_landmine=customer.get("personality_landmine", "（無）"),
        current_turn=current_turn,
        turn_pressure=get_turn_pressure(current_turn),
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 700,
        "system": system,
        "messages": messages,
    })

    response = _client.invoke_model(
        modelId=use_model,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"]


_SCORE_PATTERN = re.compile(r"總分[:：]\s*(\d{1,3})\s*/\s*100")
_DEAL_VERDICT_PATTERN = re.compile(r"成交判定[:：]\s*(成交|未成交)")
_DEAL_PRODUCT_PATTERN = re.compile(r"成交產品[:：]\s*(.+)")
_DEAL_AMOUNT_PATTERN = re.compile(r"客戶投入金額[:：]\s*([\d,，]+|未指定)")


def evaluate_session(customer: dict, history: list[dict]) -> tuple[str, int, bool, str, int]:
    """Return (evaluation_text, score, is_deal, product_name, customer_offered_amount).

    The deal verdict, product, and the amount the customer offered are all judged
    by the coach LLM. customer_offered_amount is -1 if the customer agreed but
    didn't name a figure (caller should fall back to a persona default).
    """
    conversation_text = ""
    for turn in history:
        conversation_text += f"理專：{turn['salesperson']}\n"
        conversation_text += f"客戶：{turn['customer']}\n\n"

    system = EVAL_SYSTEM.format(
        background=customer.get("background", "").strip(),
        preferred_products=customer.get("preferred_products", ""),
        disliked_products=customer.get("disliked_products", ""),
        interest_hook=customer.get("interest_hook", ""),
        personal_question=customer.get("personal_question", ""),
        personality_landmine=customer.get("personality_landmine", ""),
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2000,
        "system": system,
        "messages": [{"role": "user", "content": f"以下是完整對話紀錄：\n\n{conversation_text}"}],
    })

    response = _client.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]

    match = _SCORE_PATTERN.search(text)
    score = int(match.group(1)) if match else 50
    score = max(0, min(100, score))

    verdict_match = _DEAL_VERDICT_PATTERN.search(text)
    is_deal = bool(verdict_match and verdict_match.group(1) == "成交")

    product = ""
    offered_amount = 0
    if is_deal:
        prod_match = _DEAL_PRODUCT_PATTERN.search(text)
        if prod_match:
            product = prod_match.group(1).strip()
            if product in ("無", "—", "-", ""):
                product = ""
        if not product:
            product = "理財方案"  # fallback if LLM said 成交 but no clean product line

        amt_match = _DEAL_AMOUNT_PATTERN.search(text)
        if amt_match:
            raw = amt_match.group(1).strip()
            if raw == "未指定":
                offered_amount = -1  # caller falls back to persona default
            else:
                try:
                    offered_amount = int(raw.replace(",", "").replace("，", ""))
                except ValueError:
                    offered_amount = -1
        else:
            offered_amount = -1

    return text, score, is_deal, product, offered_amount
