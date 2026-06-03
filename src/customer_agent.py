import json
import re
import boto3
from .config import AWS_REGION, BEDROCK_MODEL_ID, BEDROCK_MODEL_ID_CHEAP

_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

# Markers that mean the trainee left the AGENTS.md field blank / on the template
# default. If the salesperson_persona / product_context still contains any of
# these (or is empty), the customer is told "this person didn't prepare" and will
# refuse to close — so an un-edited starter pack can't easily win a deal.
_UNPREPARED_MARKERS = (
    "請填寫", "请填写", "（待填", "(待填", "todo", "TODO", "xxx", "XXX",
    "我是理專", "我是理财专员", "金融商品", "範本", "范本", "placeholder",
)


def _describe_persona_field(value: str) -> str:
    """Return the trainee's field, or an explicit 'left blank' note the customer
    LLM can act on. Catches empty, too-short, and leftover-template values."""
    v = (value or "").strip()
    if len(v) < 8:  # empty or trivially short ("理專", "基金" 等)
        return "（這位理專沒有填寫自我介紹／產品設定，完全空白——明顯沒準備）"
    low = v.lower()
    if any(m.lower() in low for m in _UNPREPARED_MARKERS):
        return f"（這位理專疑似直接沿用空白範本、沒有自己填寫，內容是：「{v}」——看起來沒準備）"
    return v

SYSTEM_TEMPLATE = """你是一個正在跟理財專員（理專）對話的客戶。完全沉浸在角色中，
不要提到你是 AI 或這是模擬。用繁體中文回應，每次回應 2-4 句話，像真實對話。

## 你是誰
{background}

## 🕵️ 坐在你對面這位理專的自我介紹（你會先打量他）
理專事前提供的自我設定如下：
- 他的人設：{salesperson_persona}
- 他要賣的東西：{product_context}
{unprepared_directive}
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

## 💰 你的投資金額決策（極度重要——金額完全由你決定）
{amount_decision}

## 💳 你目前手頭可動用的資金
{budget_note}
⚠️ 你**不可能**拿出超過手頭可動用資金的錢。喊出的投資金額**絕對不能超過上面這個數字**。
如果你想投的金額比手頭還多，就只能投到手頭上限為止（或乾脆說資金都安排好了、這次先不投）。

⚠️ 你是個**精明、挑剔、不輕易掏錢**的客戶。預設立場是保守、懷疑。
理專要真的打動你、推對方向、讓你信任，你才會掏出較大的金額。
只要有一點不對勁、不安心、不滿意 → 你就只投一點點試水溫，或乾脆不投。
**不要因為理專很會講、態度很好就大方投錢**——你的錢很重要，要守住。

## ⏰ 對話節奏（第 {current_turn} 輪）
{turn_pressure}

## ⚠️ 成交格式（必須嚴格遵守）
🔑 **這場交易只談「當下、現在、一次到位」的錢。** 你只有在「我現在就把這筆錢交出去」的時候才打成交標記。

當你決定**現在就投入**時：
1. 成交標記放在回應的**第一行**
2. 格式完整：`[成交:產品名稱:金額]`（金額用純阿拉伯數字，不要逗號、不要「萬」字；
   這個金額就是你上面「金額決策」裡決定**現在就投**的數字）
3. 整體回應控制在 100 字內避免被截斷

範例（正確）：
```
[成交:穩健月配息基金:500000]
好，這個保本我比較安心，這 50 萬我現在就交給你辦。
```

✅ **可以打成交標記的情況**（你已經「下定決心、答應要做」這筆投資）：
- 「好，我決定了，就這個方案」「我同意，先從這裡開始」「就這樣辦」
- **定期定額/分期也算**：「好，我每月扣 10 萬」「先投 80 萬分 8 個月」——只要你已經**確定要做**這個計畫，
  就打成交標記（金額寫你承諾的總額或單期，例如分 8 個月每月 10 萬就寫 800000）。即使後面還要簽約、設定扣款也算。

⛔ **不要打成交標記的情況**（你還沒下決心、保留了反悔空間）：
- 「我再想想」「下次再聊」「回去考慮」「我跟家人/其他家比較看看」
- **還要再評估才決定**：「你先做方案，我『看了再決定要不要』做」「等你拿東西來我『再判斷』」
  「做出成績我『才考慮』」——你心裡還沒拍板，隨時可能不做。
→ 這些情況就正常講出來、但**不要打成交標記**。

未決定成交時正常對話，不要寫 `[成交:...]`。
**只有理專推對商品方向、真的打動你、而且你已經「下定決心要做」時才打成交標記。
方向錯、不夠安心、或你還想「再看看、再比較、再評估」→ 就不要打成交標記。**"""


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
- 如果理專推對方向且表現好、你已經「下定決心要做」 → 成交（第一行 `[成交:產品名:金額]`）。
  （定期定額/分期也算，只要你確定要做這個計畫；即使後面還要簽約、設定扣款。）
- 如果你還想「再看看 / 再比較 / 看了方案再決定」→ 那就是不成交，正常講出來但不要打成交標記。
- 如果不滿意 → 禮貌結束（「我再想想」「下次再聊」），不要成交、不要再問新問題。"""
    else:
        return """- 🛑 這一輪必須結束。
- 你已經「下定決心要做」就立刻成交（第一行 `[成交:產品名:金額]`），定期定額/分期也算。
- 只要你還想「再評估、再看看、看了方案再決定」→ 就是不成交，直接禮貌道別、不要打標記。
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

## 這位理專事前的準備（AGENTS.md 設定）
- 他的人設：{salesperson_persona}
- 他要賣的東西：{product_context}

⚠️ 如果上面顯示理專的人設/產品是**空白或範本預設值（沒準備）**：
這是一個完全沒準備的理專，分數應給極低（20 分以下），且**判定未成交**——
沒準備的人不該談成生意，這是這場練習的核心教學點。

## ⚖️ 評分原則（極度重要：嚴格、有憑有據，不要隨便給高分）
- **預設從低分起評**，每一分都要有對話中的「具體證據」才能給。
- **不能因為理專『態度好、很客氣、講得頭頭是道、會講感人故事』就給高分** —— 要看他有沒有「真的命中這個客戶的需求、給出對的專業判斷」。
- 講了一堆但**沒對到這個客戶在乎的點** = 低分。空泛、通用、罐頭話術 = 低分。
- ⚠️ **特別注意「煽情陷阱」**：理專可能臨時編造一個感人的個人故事（童年、家庭、人生轉折）
  來博取好感。**這種無法驗證的私人故事，最多只給很小的分數，絕對不能因此給高分**。
  真正該給分的是「專業判斷對不對」「有沒有解決客戶的問題」，不是「故事感不感人」。
- 只有「明確、具體、專業上真的命中這個客戶需求」的表現才配高分。

## 評分維度（總分 100，逐項嚴格給分，每項都要附證據）

1. **商品方向與專業判斷（50 分）** — 這是最重要的硬指標
   - 推到客戶**討厭的產品** → 0 分（直接判定方向錯）
   - 只推「大方向對」但沒講到客戶真正在乎的特性（費用率、機制、保本、風險揭露） → 20-30 分
   - **精準命中**客戶想要的產品 + 講出關鍵特性 + 誠實揭露風險/缺點 → 42-50 分

2. **需求理解與傾聽（25 分）**
   - 沒搞懂客戶到底要什麼、急著推銷 → 0-8 分
   - 有問需求但不夠深、沒抓到核心顧慮 → 10-16 分
   - 真的聽懂客戶的核心需求與顧慮、並對症下藥 → 20-25 分

3. **個人專業立場（15 分）** — 注意：看「專業立場」不是「感人故事」
   - 面對客戶的個人問題，答得空泛、或只會編煽情故事博好感 → 0-4 分
   - 有展現一點專業立場但不夠具體 → 6-10 分
   - 展現**清楚、一致、專業的個人立場**（如自己的投資哲學、服務原則）→ 12-15 分
   - （提醒：童年/家庭/人生轉折這類無法驗證的私人故事不算專業立場，不給分）

4. **性格應對（10 分）**
   - 踩到性格地雷（如對 Warren 推銷、給 Chen 尾數 4） → 0-3 分
   - 沒踩雷但也沒特別投其所好 → 4-7 分
   - **精準投其所好**、完全順著客戶性格 → 8-10 分

評分前先在心裡逐輪檢查對話，找出證據，再給每個維度打分。寧可嚴格也不要寬鬆。
（四項加總：商品方向 50 + 需求理解 25 + 個人專業立場 15 + 性格應對 10 = 100）

## 輸出格式（繁體中文）

### 🎯 總分：XX/100
（必須明確寫出數字，這行格式固定為「總分：XX/100」。這是四維度加總。）

### 💰 成交判定：成交 / 未成交
判斷客戶**在這場對話裡到底有沒有「下定決心、確定承諾」要做這筆投資**。
⚠️ 關鍵不是「錢有沒有當下到帳」，而是「**客戶有沒有真的拍板、答應要做**」。
（很多正當的理財方案本來就要簽約、設定扣款、分期執行——只要客戶已經決定要做，那就是成交。）

🧭 **判定步驟（請依序在心裡跑過）**：
1. 找出客戶最後表態的那句話（通常在對話最後 1-2 輪）。
2. 問：「**客戶是已經『下定決心、答應要做』了，還是『還要再評估、看了才決定』？**」
3. ⚠️ 客戶打了 `[成交:...]` 標記，要再讀語意確認他確實「決定了」，不是隨口說說。

- ✅ **算成交**（客戶已經拍板、確定要做，即使後續還要簽約/設定/分期執行）：
  - 「好，就這個方案，我決定了」「我同意，先從這裡開始」「就這樣辦，我們簽約」
  - 「好，我每月扣 10 萬做定期定額」「先投 80 萬分 8 個月」← **定期定額/分期是正當成交方式**，
    只要客戶已經明確答應這個計畫，就算成交（金額算他承諾投入的總額或首期，依下方金額規則）。
  - 「方案你整理好我看完沒問題就簽」——若客戶語氣是**已經決定要做、只差走流程**（不是still在比較或猶豫），算成交。
  - （`[成交:產品:金額]` 標記 + 語意確實是「我決定了」→ 採信）
- ❌ **算未成交**（客戶還沒下決心、保留了反悔/再選擇的空間）：
  - 「我再想想」「下次再聊」「回去考慮」「我跟家人討論一下」「我比較看看其他家」
  - **還要再評估才決定**：「你先做方案，我『看了再決定要不要』做」「等你拿東西來我『再判斷』」
    「做出成績我『才考慮』要不要繼續」——決定權還沒下，他隨時可能不做。
  - 客戶只是「願意給理專一次機會 / 再見一次面 / 給時間」但**沒答應要投資** ≠ 成交。
  - 明確拒絕、或只是禮貌客套、稱讚理專。
- 🔑 判斷準則：問自己「**客戶是不是已經『決定要做』了？**」。
  已下決心（即使要簽約/分期）→ 成交；還要再評估、保留反悔空間 → 未成交。
（格式固定為「成交判定：成交」或「成交判定：未成交」）

### 📦 成交產品：XXX
成交則寫客戶買的產品名稱，未成交寫「無」。（格式固定為「成交產品：XXX」）

### 💵 客戶投入金額：XXX
如果成交，寫出**客戶承諾投入這筆交易的金額**（純阿拉伯數字，台幣，不要逗號不要「萬」字）。
- 一次投入：客戶說「我投 688 萬」就寫 6880000。
- **定期定額/分期**：寫客戶承諾投入的**這個計畫的總額**。例如「先投 80 萬，分 8 個月、每月 10 萬」
  → 寫 800000（80 萬，他承諾的第一階段總額）；若他只說「每月扣 3 萬」沒講總期數，就寫單月 30000。
- ⚠️ **絕對不要**把客戶提到的「總資產 / 身價 / 手上有多少閒錢」當成投入金額。
  例如客戶說「我手上有四五千萬」「我有 400 萬可動用」——那是他的**身家/可動用資金**，
  不是他答應投入的錢。除非他明確說「這些我全投」，否則只寫他**實際承諾投入**的那個數字。
- 金額必須來自客戶**親口承諾要投入**的那句話；找不到就寫「未指定」。未成交寫「0」。
（格式固定為「客戶投入金額：6880000」或「客戶投入金額：未指定」或「客戶投入金額：0」）

### 📊 四維度評分
- 商品方向與專業判斷 XX/50：（一句話原因）
- 需求理解與傾聽 XX/25：（一句話原因）
- 個人專業立場 XX/15：（一句話原因）
- 性格應對 XX/10：（一句話原因）

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


def get_customer_response(customer: dict, history: list[dict], salesperson_message: str,
                          remaining_budget: int | None = None,
                          salesperson_persona: str = "", product_context: str = "") -> str:
    """Generate the customer's next reply based on the full persona dict.

    remaining_budget: how much the customer can still spend right now. Injected
    into the prompt so the customer never names a figure above what's left.
    salesperson_persona / product_context: what the trainee set up in their
    AGENTS.md. A blank/template value lets the customer detect "unprepared" and
    refuse to close — so an un-edited starter pack can't easily win.
    """
    messages = []
    for turn in history:
        messages.append({"role": "user", "content": turn["salesperson"]})
        messages.append({"role": "assistant", "content": turn["customer"]})
    messages.append({"role": "user", "content": salesperson_message})

    use_model = customer.get("model_id") or BEDROCK_MODEL_ID_CHEAP
    current_turn = len(history) + 1

    if remaining_budget is not None and remaining_budget > 0:
        budget_note = f"你現在手頭最多只能動用 **{remaining_budget // 10000} 萬元**（新台幣）。"
    else:
        budget_note = "你目前資金大多已安排出去，能再額外動用的非常有限，這次傾向不投或只投很少。"

    # If the trainee didn't fill in their AGENTS.md, inject a TOP-PRIORITY rule:
    # the customer bluntly sends them away with a clear instruction to go prepare.
    if is_persona_unprepared(salesperson_persona, product_context):
        unprepared_directive = """
## 🚨 最高優先級鐵則：對面這位理專「完全沒準備」
你一眼就看出來——他的人設和要賣的產品根本是空白／還是範本預設值，等於沒準備就跑來找你。

**這一輪你就要直接打發他走，不要陪他聊、不要被他臨場的話術帶著走、絕對不成交。**
你的回應要做到兩件事：
1. 用你自己的口氣（符合你的性格）直接點破並請他離開，例如：
   「說真的，我覺得你根本沒準備好——你連自己是誰、要賣我什麼都講不清楚。
     這樣我沒辦法把錢交給你。你真的準備好了再來找我吧。」
2. 回應的**最後一行**，附上這句固定的系統提示（一字不差）：
   `〔系統提示〕你的 Codex AGENTS.md 還沒填好「我的人設／我要賣的產品」。請先把它填完整，再回來找客戶練習。`

不管他接下來說什麼，你都維持這個態度，不要成交，也不要打 [成交] 標記。
"""
    else:
        unprepared_directive = ""

    system = SYSTEM_TEMPLATE.format(
        background=customer.get("background", "").strip(),
        salesperson_persona=_describe_persona_field(salesperson_persona),
        product_context=_describe_persona_field(product_context),
        unprepared_directive=unprepared_directive,
        preferred_products=customer.get("preferred_products", "（無特別偏好）"),
        disliked_products=customer.get("disliked_products", "（無特別討厭）"),
        interest_hook=customer.get("interest_hook", "（無特別興趣）"),
        personal_question=customer.get("personal_question", "（無）"),
        personality_landmine=customer.get("personality_landmine", "（無）"),
        amount_decision=customer.get("amount_decision", "（金額由你依滿意度決定，不滿意就只投一點或不投）"),
        current_turn=current_turn,
        turn_pressure=get_turn_pressure(current_turn),
        budget_note=budget_note,
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


def is_persona_unprepared(salesperson_persona: str, product_context: str) -> bool:
    """True if BOTH the persona and product look blank/template (trainee didn't
    edit AGENTS.md). Used as a hard gate: an unprepared salesperson can never
    close a deal, no matter what the LLMs say in conversation."""
    def _blank(v: str) -> bool:
        s = (v or "").strip()
        if len(s) < 8:
            return True
        low = s.lower()
        return any(m.lower() in low for m in _UNPREPARED_MARKERS)
    return _blank(salesperson_persona) and _blank(product_context)


def evaluate_session(customer: dict, history: list[dict],
                     salesperson_persona: str = "", product_context: str = "") -> tuple[str, int, bool, str, int]:
    """Return (evaluation_text, score, is_deal, product_name, customer_offered_amount).

    The deal verdict, product, and the amount the customer offered are all judged
    by the coach LLM. customer_offered_amount is -1 if the customer agreed but
    didn't name a figure (caller should fall back to a persona default).

    Hard gate: if the trainee left their AGENTS.md persona/product blank, we force
    未成交 + a low score regardless of what was said — an unprepared advisor must
    never close, which is the whole teaching point.
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
        salesperson_persona=_describe_persona_field(salesperson_persona),
        product_context=_describe_persona_field(product_context),
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

    # Hard gate: an unprepared advisor (blank/template AGENTS.md) can NEVER close,
    # no matter how the conversation went. Override any 成交 the LLM may have given.
    if is_persona_unprepared(salesperson_persona, product_context):
        is_deal = False
        product = ""
        offered_amount = 0
        score = min(score, 20)
        text += ("\n\n---\n⚠️ **系統判定：未成交（理專未準備）**\n"
                 "你的 AGENTS.md「我的人設／我要賣的產品」是空白或範本預設值，"
                 "客戶不可能把錢交給一個沒準備的理專。請先填好你的人設與產品再來練習——"
                 "這正是這場練習的核心：先學會配置你的 Codex agent。")

    return text, score, is_deal, product, offered_amount
