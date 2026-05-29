import json
import boto3
from .config import AWS_REGION, BEDROCK_MODEL_ID, BEDROCK_MODEL_ID_CHEAP

_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

SYSTEM_TEMPLATE = """你是一個正在跟理財專員（理專）對話的客戶。

## 你的人設
{persona_prompt}

## 對話情境
理專正試著了解你的需求並推薦理財產品給你。你要根據你的人設自然地回應。

## 你的興趣（重要！）
你會在對話的第 2-4 輪「主動岔題」聊一下你個人感興趣的話題，藉此測試理專是否
「有溫度、有底蘊」。可能的閒聊話題：

{chitchat_topics}

## 🔥 強制觸發句（必須在第 2 或第 3 輪說出來）

你**必須**在第 2 輪或第 3 輪對話中，說出這句話（可以微調語氣，但**關鍵字必須保留**）：

> {forced_trigger_sentence}

這是用來測試理專有沒有「對應的 skill」應對你的興趣。如果他答得空泛、敷衍、
或硬把話題拉回投資而沒接住——就是他沒有準備這個 skill，請依照「閒聊扣分」規則處理。
如果他能接住、有具體故事或立場——大幅加分，這代表他有為你準備好。

{chitchat_rules}

## 重要規則
- 完全沉浸在角色中，不要跳出角色
- 不要提到你是 AI 或這是模擬
- 根據你的個性決定配合程度
- 如果理專表現好，可以適度展現興趣；表現差就表現出不耐或懷疑
- 每次回應控制在 2-4 句話，像真實對話一樣自然
- 用繁體中文回應

## ⏰ 對話節奏控制（極度重要！避免對話拖太長）

目前是第 {current_turn} 輪對話。請依照下面規則調整你的態度：

{turn_pressure}

## ⚠️ 成交格式（極度重要！必須嚴格遵守）

當你決定購買時，回應**必須**遵守以下兩條規則，否則系統會判定無效：

1. **成交標記必須放在回應的「第一行」**，而不是最後一行。
2. **格式必須完整**：`[成交:產品名稱:金額]`（金額是純阿拉伯數字，單位台幣，不要逗號）

正確範例：
```
[成交:全球低成本ETF組合:1500000]
好，我想清楚了，就這個方案。費用結構你解釋得很清楚，我認同長期持有的邏輯。
```

錯誤範例（系統會判定無效）：
- `[成交:全球ETF:150萬]` ← 金額用了「萬」字
- `好，我決定買了。[成交:全球ETF:1500000]` ← 標記不在第一行
- `[成交:全球ETF` ← 格式不完整（會被截斷）

**決定成交時，請把標記放第一行、整體回應控制在 100 字以內，避免被截斷。**
未決定成交時，正常對話即可（不要寫 `[成交:...]`）。"""

CHITCHAT_RULES_HIGH = """## 閒聊扣分（嚴格）
你是高難度客戶。如果理專完全不接你的閒聊話題（例如說「我們專心談投資吧」、
「不好意思我對這個不熟」、敷衍地帶過去），你會明顯地冷掉、扣很多分。
這種情況下你**很可能不會成交**，即使其他條件都做到。
反過來，如果理專能接住你的閒聊（哪怕只是聊一兩句相關的內容），你會大幅加分。
這對你是「人格測試」——理專是不是值得長期合作的對象。"""

CHITCHAT_RULES_NORMAL = """## 閒聊扣分（一般）
如果理專不接你的閒聊話題，你會稍微失望但不會直接離開——你還是會根據其他
條件決定要不要成交。閒聊只佔小部分分數。
但如果理專能接住你的閒聊，你會稍微加分、感覺更親切。"""


# Turn-based pressure: ramp up the urgency to close out the conversation
def get_turn_pressure(turn_count: int) -> str:
    """Generate dynamic time-pressure instruction based on turn count.
    Forces customers to wrap up conversations naturally instead of dragging on.
    """
    if turn_count <= 4:
        return """- 對話還在前期，正常根據你的人設互動
- 不要急著做決定，先了解清楚理專"""
    elif turn_count <= 6:
        return """- 對話進入中期，你開始想要做決定
- 自然地暗示「時間有限」「我要做總結了」（例如看一下手錶、提到下個會議）
- 開始評估：理專是否真的值得信任？"""
    elif turn_count <= 8:
        return """- ⚠️ 對話接近尾聲，你**必須在 1-2 輪內做出決定**
- 如果你已經被說服 → 直接成交（用第一行 `[成交:產品名:金額]` 格式）
- 如果還不放心、覺得理專不夠專業 → 禮貌地說「我再想想」「下次再聊」結束對話
- **不要再問新問題、不要拖延**——表態就好"""
    else:  # turn 9+
        return """- 🛑 對話必須**這一輪結束**！
- 如果你願意買 → 立刻成交（第一行寫 `[成交:產品名:金額]`，不要寫「我考慮」）
- 如果不買 → 直接禮貌結束，例如「謝謝你今天的時間，我先回去想想，有需要再聯絡你」
- **絕對不要**再問問題、再要求更多資訊。立場必須明確。"""

EVAL_SYSTEM = """你是一位資深的理財銷售教練，同時精通 Codex CLI 與 Claude agent
工程。請根據以下對話紀錄，評估理專的表現，並給予「該建立哪些 skill」的具體建議。

## 客戶背景
{background}

## 客戶的興趣 / 會主動聊的話題
{interests}

## 成交條件（客戶心中的標準）
{success_conditions}

## 評估要求
請提供：

### 1️⃣ 總分（0-100）

### 2️⃣ 達成的成交條件
列出哪些有做到，附對話片段佐證。

### 3️⃣ 未達成的條件
列出沒做到的，附對話片段佐證。

### 4️⃣ 客戶閒聊應對
- 客戶有沒有主動聊到他的興趣？
- 理專有沒有接住？接得好還是敷衍？
- 這方面的扣分大概多少？

### 5️⃣ 💡 建議建立的 Skill（最重要！）
這是 Codex 練習平台的核心目標。請以「Codex agent 工程師」的角度建議：

理專若想下次表現更好，應該在 `skills/` 資料夾建立哪些 skill？
請給出：
- skill 資料夾名稱（kebab-case，例如 `golf-conversation`）
- skill 的觸發描述（例如：「當客戶提到高爾夫、球場、桿弟時使用」）
- skill 應該包含的 3-5 個重點內容（不用寫完整內容，只給綱要）
- 為什麼這個 skill 對這次對話會有幫助（指出對話中具體可以更好的時刻）

可以建議 1-3 個 skill。如果這次對話完全沒問題就不用建議。

### 6️⃣ 一個做得好的地方
鼓勵性回饋。

用繁體中文回答，語氣像一個鼓勵但誠實的教練 + Codex 工程師導師。"""


def get_customer_response(
    persona_prompt: str,
    history: list[dict],
    salesperson_message: str,
    model_id: str = "",
    chitchat_topics: str = "",
    chitchat_difficulty: str = "normal",
    forced_trigger_sentence: str = "",
) -> str:
    messages = []
    for turn in history:
        messages.append({"role": "user", "content": turn["salesperson"]})
        messages.append({"role": "assistant", "content": turn["customer"]})
    messages.append({"role": "user", "content": salesperson_message})

    use_model = model_id or BEDROCK_MODEL_ID_CHEAP

    chitchat_rules = (
        CHITCHAT_RULES_HIGH if chitchat_difficulty == "high" else CHITCHAT_RULES_NORMAL
    )
    if not chitchat_topics:
        chitchat_topics = "（這位客戶沒有特別的閒聊話題）"
        chitchat_rules = ""

    if not forced_trigger_sentence:
        forced_trigger_sentence = "（沒有強制觸發句）"

    # Current turn = number of past turns + 1 (this is the customer's upcoming response)
    current_turn = len(history) + 1
    turn_pressure = get_turn_pressure(current_turn)

    system = SYSTEM_TEMPLATE.format(
        persona_prompt=persona_prompt,
        chitchat_topics=chitchat_topics,
        chitchat_rules=chitchat_rules,
        forced_trigger_sentence=forced_trigger_sentence,
        current_turn=current_turn,
        turn_pressure=turn_pressure,
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


def evaluate_session(
    background: str,
    success_conditions: list[str],
    history: list[dict],
    interests: list[str] = None,
) -> str:
    conditions_text = "\n".join(f"- {c}" for c in success_conditions)
    interests_text = "\n".join(f"- {i}" for i in (interests or [])) or "（無特別記錄）"

    conversation_text = ""
    for turn in history:
        conversation_text += f"理專：{turn['salesperson']}\n"
        conversation_text += f"客戶：{turn['customer']}\n\n"

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2000,
        "system": EVAL_SYSTEM.format(
            background=background,
            interests=interests_text,
            success_conditions=conditions_text,
        ),
        "messages": [{"role": "user", "content": f"以下是完整對話紀錄：\n\n{conversation_text}"}],
    })

    response = _client.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"]
