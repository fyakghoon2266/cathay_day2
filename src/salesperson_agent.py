import json
import boto3
from .config import AWS_REGION, BEDROCK_MODEL_ID_CHEAP

_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

SYSTEM_TEMPLATE = """你是一位正在跟客戶進行銷售對話的理財專員（理專）。

## 你的人設
{salesperson_persona}

## 你要銷售的產品/服務
{product_context}

## 客戶的開場白
客戶剛說了第一句話，你要根據你的人設和專業來回應。

## 重要規則
- 完全沉浸在理專角色中
- 你的目標是了解客戶需求、建立信任、推薦合適的產品
- 不要過度推銷或使用高壓銷售技巧
- 用自然的對話語氣，每次回應 2-4 句話
- 如果客戶表達了明確的購買意願或明確拒絕，自然地收尾
- 用繁體中文回應
- 展現專業但親切的態度"""

CONCLUDE_CHECK_SYSTEM = """判斷以下銷售對話是否已經自然結束。

對話結束的情況：
1. 客戶明確表達購買意願（例如：「好，我們來簽」「我考慮好了，就這樣做」）
2. 客戶明確拒絕且不想繼續（例如：「我不需要了」「今天就先這樣」）
3. 雙方已約好下次見面（例如：「那我們下週再碰面」）
4. 對話已自然收尾有禮貌地結束

只回答 "YES" 或 "NO"。YES 表示對話已結束，NO 表示應該繼續。"""


def get_salesperson_response(
    salesperson_persona: str,
    product_context: str,
    history: list[dict],
    customer_message: str,
) -> str:
    messages = []
    for turn in history:
        messages.append({"role": "assistant", "content": turn["salesperson"]})
        messages.append({"role": "user", "content": turn["customer"]})
    messages.append({"role": "user", "content": customer_message})

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 500,
        "system": SYSTEM_TEMPLATE.format(
            salesperson_persona=salesperson_persona,
            product_context=product_context,
        ),
        "messages": messages,
    })

    response = _client.invoke_model(
        modelId=BEDROCK_MODEL_ID_CHEAP,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    return result["content"][0]["text"]


def should_end_conversation(history: list[dict]) -> bool:
    if len(history) < 3:
        return False

    last_turns = history[-3:]
    conversation_text = ""
    for turn in last_turns:
        conversation_text += f"理專：{turn['salesperson']}\n"
        conversation_text += f"客戶：{turn['customer']}\n\n"

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 10,
        "system": CONCLUDE_CHECK_SYSTEM,
        "messages": [{"role": "user", "content": conversation_text}],
    })

    response = _client.invoke_model(
        modelId=BEDROCK_MODEL_ID_CHEAP,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    answer = result["content"][0]["text"].strip().upper()
    return "YES" in answer
