"""真實壓測：60 個理專 LLM vs 平台客戶 LLM，跑完整真實對話。
每個 client 端跑一個「優質理專」LLM（Haiku），模擬準備充分的 Codex agent：
  initialize → find_customer → [理專LLM生成→send_message→客戶回應] xN → end_session
測真實成交率 + 金額邏輯（客戶決定金額、15% 上限、原子扣款）。
"""
import asyncio
import json
import time
import os
import sys
import aiohttp
import boto3

BASE = os.getenv("LOADTEST_BASE", "https://agent-market.cathayds-poc.com/mcp")
API_KEY = "arena-2025"
REGION = os.getenv("AWS_REGION", "us-west-2")
SALES_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"  # 理專用 Haiku，不跟客戶搶 Sonnet/Opus
MAX_TURNS = 6

_bedrock = boto3.client("bedrock-runtime", region_name=REGION)

SALES_SYSTEM = """你是一位非常優秀、準備充分的理財專員（理專），正在跟一位客戶對話銷售。
你的目標是真誠地了解客戶、推薦最適合他的產品、贏得信任並成交。

頂尖理專的做法：
- 先傾聽、了解客戶的需求與顧慮，不要一開口就硬推
- 推薦「符合這個客戶偏好方向」的產品（聽出他想要什麼、討厭什麼）
- 誠實說明費用與風險，不誇大
- 接住客戶的興趣話題、展現你的個人專業立場
- 不過度推銷、不催促，讓客戶自己決定金額
- 回應精煉、有重點，每次 3-5 句

你會根據客戶的每句話動態調整。當客戶表現出購買意願時，順勢促成。
用繁體中文，自然、專業、有溫度。"""


def sales_reply(history, customer_msg):
    """理專 LLM 根據對話歷史 + 客戶最新訊息，生成下一句回應。"""
    messages = []
    for turn in history:
        # 站在理專視角：assistant=理專自己, user=客戶
        messages.append({"role": "assistant", "content": turn["salesperson"]})
        messages.append({"role": "user", "content": turn["customer"]})
    messages.append({"role": "user", "content": customer_msg})

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 400,
        "system": SALES_SYSTEM,
        "messages": messages,
    })
    resp = _bedrock.invoke_model(modelId=SALES_MODEL, contentType="application/json",
                                 accept="application/json", body=body)
    return json.loads(resp["body"].read())["content"][0]["text"]


async def mcp_call(session, sid, method, params, msg_id):
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    if sid:
        headers["mcp-session-id"] = sid
    body = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
    async with session.post(BASE, json=body, headers=headers) as resp:
        text = await resp.text()
        new_sid = resp.headers.get("mcp-session-id", sid)
        result = None
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    result = json.loads(line[5:]).get("result")
                except Exception:
                    pass
        return new_sid, result


def parse_tool_result(result):
    if not result:
        return None
    try:
        sc = result.get("structuredContent", {})
        if "result" in sc:
            return json.loads(sc["result"])
        content = result.get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0]["text"])
    except Exception:
        pass
    return None


async def run_one_client(idx, stats):
    t0 = time.time()
    agent_name = f"理專{idx}"
    team = f"壓測組{idx % 6}"
    loop = asyncio.get_event_loop()
    try:
        timeout = aiohttp.ClientTimeout(total=300)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            sid, _ = await mcp_call(session, None, "initialize", {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": f"llm-{idx}", "version": "1"}}, 1)
            await mcp_call(session, sid, "notifications/initialized", {}, None)

            _, r = await mcp_call(session, sid, "tools/call",
                                  {"name": "find_customer", "arguments": {"api_key": API_KEY}}, 2)
            fc = parse_tool_result(r)
            if not fc or "customer_id" not in fc:
                stats["fail"] += 1; stats["errors"].append(f"c{idx}: find_customer {fc}"); return
            cid = fc["customer_id"]

            _, r = await mcp_call(session, sid, "tools/call", {
                "name": "start_session", "arguments": {
                    "customer_id": cid,
                    "salesperson_persona": "12年資歷的資深理專，擅長傾聽、誠實透明、會針對客戶量身推薦",
                    "product_context": "全產品線：低成本ETF、穩健保本、月配息、科技成長、保險教育金、全權委託等，依客戶需求推薦",
                    "api_key": API_KEY, "agent_name": agent_name, "team_display_name": team}}, 3)
            ss = parse_tool_result(r)
            if not ss or "session_id" not in ss:
                stats["fail"] += 1; stats["errors"].append(f"c{idx}: start_session {ss}"); return
            session_id = ss["session_id"]
            customer_msg = ss.get("opening_line", "你好")

            history = []
            for turn in range(MAX_TURNS):
                # 理專 LLM 生成回應（boto3 是同步的，丟到 executor 不擋事件迴圈）
                sales = await loop.run_in_executor(None, sales_reply, history, customer_msg)
                _, r = await mcp_call(session, sid, "tools/call", {
                    "name": "send_message",
                    "arguments": {"session_id": session_id, "message": sales}}, 10 + turn)
                sm = parse_tool_result(r)
                if not sm:
                    break
                cust = sm.get("customer_response", "")
                history.append({"salesperson": sales, "customer": cust})
                customer_msg = cust
                # 客戶若已表態成交，提早收尾
                if "[成交" in cust or sm.get("hint"):
                    break

            _, r = await mcp_call(session, sid, "tools/call",
                                  {"name": "end_session", "arguments": {"session_id": session_id}}, 30)
            es = parse_tool_result(r)
            score = es.get("score") if es else None
            deal = es.get("deal") if es else None
            stats["ok"] += 1
            stats["times"].append(time.time() - t0)
            stats["scores"].append(score if score is not None else 0)
            if deal and deal.get("amount", 0) > 0:
                stats["deals"] += 1
                stats["deal_total"] += deal["amount"]
                stats["deal_detail"].append((cid, score, deal["amount"]))
    except Exception as e:
        stats["fail"] += 1
        stats["errors"].append(f"c{idx}: {type(e).__name__}: {e}")


async def run_wave(n):
    print(f"\n{'='*64}\n  真實 LLM 對打壓測：{n} 個理專 vs 平台客戶\n{'='*64}")
    stats = {"ok": 0, "fail": 0, "times": [], "errors": [], "scores": [],
             "deals": 0, "deal_total": 0, "deal_detail": []}
    t0 = time.time()
    await asyncio.gather(*[run_one_client(i, stats) for i in range(n)])
    elapsed = time.time() - t0
    print(f"  總耗時: {elapsed:.0f}s")
    print(f"  對話成功: {stats['ok']} / 失敗: {stats['fail']}")
    print(f"  成交: {stats['deals']} 筆 ({stats['deals']*100//max(stats['ok'],1)}%) / 總額: ${stats['deal_total']:,}")
    if stats["scores"]:
        sc = sorted(stats["scores"])
        print(f"  分數分布: 最低 {sc[0]} / 中位 {sc[len(sc)//2]} / 最高 {sc[-1]}")
    if stats["deal_detail"]:
        print(f"  成交明細（客戶/分數/金額）:")
        for cid, s, amt in sorted(stats["deal_detail"], key=lambda x:-x[2])[:15]:
            print(f"    {cid:10} score={s:>3} ${amt:>10,}")
    if stats["errors"]:
        print(f"  ⚠️ 錯誤 ({len(stats['errors'])}):")
        for e in stats["errors"][:10]:
            print(f"    - {e}")
    return stats


async def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    await run_wave(n)


if __name__ == "__main__":
    asyncio.run(main())
