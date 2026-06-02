"""壓力測試：模擬 N 個並發 MCP client 跑完整對話流程。
每個 client：initialize → find_customer → start_session → send_message x4 → end_session
打的是跟真 Codex 一模一樣的 MCP 端點，所以 server 分不出差別。
"""
import asyncio
import json
import time
import random
import sys
import aiohttp

BASE = "http://127.0.0.1:8765/mcp"
API_KEY = "arena-2025"
# 壓測模式：所有 client 都打 loadtest 客戶（保證成交，測扣款/排行榜/併發）
LOADTEST_MODE = True

# 理專會說的話（隨機挑，模擬不同表現）
SALES_LINES = [
    "您好，我是專做穩健配置的理專，想先了解您的需求和目標。",
    "根據您的狀況，我建議低成本的指數型 ETF，長期持有、費用透明。",
    "我理解您的顧慮，這個產品的風險我會完整說明，包括最壞情況。",
    "我們可以從定期定額開始，金額您決定，不用一次投入太多。",
    "這個配置兼顧成長與穩健，我自己也是這樣規劃的。",
    "如果您願意，我們今天可以先小額開始，之後再調整。",
]


async def mcp_call(session, sid, method, params, msg_id):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if sid:
        headers["mcp-session-id"] = sid
    body = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
    async with session.post(BASE, json=body, headers=headers) as resp:
        text = await resp.text()
        new_sid = resp.headers.get("mcp-session-id", sid)
        # 解析 SSE
        result = None
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    d = json.loads(line[5:])
                    result = d.get("result")
                except Exception:
                    pass
        return new_sid, result


def parse_tool_result(result):
    """從 tools/call 回傳取出實際 JSON 內容"""
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
    """一個 client 跑完整流程"""
    t0 = time.time()
    agent_name = f"壓測員{idx}"
    team = f"壓測隊{idx % 6}"
    try:
        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # 1. initialize
            sid, _ = await mcp_call(session, None, "initialize", {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": f"loadtest-{idx}", "version": "1"},
            }, 1)
            # initialized notification
            await mcp_call(session, sid, "notifications/initialized", {}, None)

            # 2. 選客戶：壓測模式直接指定 loadtest（保證成交，測扣款/排行榜/race）
            if LOADTEST_MODE:
                cid = "loadtest"
            else:
                _, r = await mcp_call(session, sid, "tools/call", {
                    "name": "find_customer", "arguments": {"api_key": API_KEY},
                }, 2)
                fc = parse_tool_result(r)
                if not fc or "customer_id" not in fc:
                    stats["fail"] += 1
                    stats["errors"].append(f"client{idx}: find_customer failed: {fc}")
                    return
                cid = fc["customer_id"]

            # 3. start_session
            _, r = await mcp_call(session, sid, "tools/call", {
                "name": "start_session", "arguments": {
                    "customer_id": cid,
                    "salesperson_persona": "10年經驗的穩健型理專，誠實透明",
                    "product_context": "低成本ETF、穩健配置、定期定額",
                    "api_key": API_KEY,
                    "agent_name": agent_name,
                    "team_display_name": team,
                },
            }, 3)
            ss = parse_tool_result(r)
            if not ss or "session_id" not in ss:
                stats["fail"] += 1
                stats["errors"].append(f"client{idx}: start_session failed: {ss}")
                return
            session_id = ss["session_id"]

            # 4. send_message x4
            for turn in range(4):
                _, r = await mcp_call(session, sid, "tools/call", {
                    "name": "send_message", "arguments": {
                        "session_id": session_id,
                        "message": random.choice(SALES_LINES),
                    },
                }, 10 + turn)
                sm = parse_tool_result(r)
                if not sm:
                    stats["errors"].append(f"client{idx}: send_message turn{turn} no result")
                    break

            # 5. end_session
            _, r = await mcp_call(session, sid, "tools/call", {
                "name": "end_session", "arguments": {"session_id": session_id},
            }, 20)
            es = parse_tool_result(r)
            deal = es.get("deal") if es else None
            if deal and deal.get("amount", 0) > 0:
                stats["deals"] += 1
                stats["deal_total"] += deal["amount"]

            stats["ok"] += 1
            stats["times"].append(time.time() - t0)
            stats["customers"][cid] = stats["customers"].get(cid, 0) + 1
    except asyncio.TimeoutError:
        stats["fail"] += 1
        stats["errors"].append(f"client{idx}: TIMEOUT (>180s)")
    except Exception as e:
        stats["fail"] += 1
        stats["errors"].append(f"client{idx}: {type(e).__name__}: {e}")


async def run_wave(n):
    print(f"\n{'='*60}")
    print(f"  壓測 {n} 個並發 client")
    print(f"{'='*60}")
    stats = {"ok": 0, "fail": 0, "times": [], "errors": [], "customers": {},
             "deals": 0, "deal_total": 0}
    t0 = time.time()
    await asyncio.gather(*[run_one_client(i, stats) for i in range(n)])
    elapsed = time.time() - t0

    print(f"  總耗時: {elapsed:.1f}s")
    print(f"  成功: {stats['ok']} / 失敗: {stats['fail']}")
    print(f"  成交: {stats['deals']} 筆 / 成交總額: ${stats['deal_total']:,}")
    if stats["times"]:
        ts = sorted(stats["times"])
        print(f"  單場對話耗時: 最快 {ts[0]:.1f}s / 中位 {ts[len(ts)//2]:.1f}s / 最慢 {ts[-1]:.1f}s")
    print(f"  客戶分布: {dict(sorted(stats['customers'].items(), key=lambda x:-x[1]))}")
    if stats["errors"]:
        print(f"  ⚠️ 錯誤 ({len(stats['errors'])}):")
        for e in stats["errors"][:15]:
            print(f"    - {e}")
    return stats


async def main():
    waves = [int(x) for x in sys.argv[1:]] or [20, 40, 60]
    for n in waves:
        await run_wave(n)
        await asyncio.sleep(3)  # 波次之間喘口氣


if __name__ == "__main__":
    asyncio.run(main())
