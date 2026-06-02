import json
import random
from fastmcp import FastMCP
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from src.config import MCP_PORT, MAX_TURNS
from src.personas_loader import get_all_customers, get_customer, get_customers_by_tags, load_personas
from src.session_manager import (
    create_session,
    get_session,
    add_turn,
    end_session as end_session_db,
    is_turn_limit_reached,
)
from src.customer_agent import get_customer_response, evaluate_session
from src.salesperson_agent import get_salesperson_response, should_end_conversation
from src.auth import validate_key
from src.transcript import save_transcript
from src.arena import (
    init_customer_budget,
    get_remaining_budget,
    deduct_budget,
    detect_deal,
    final_deal_amount,
    record_deal,
    get_leaderboard,
    get_team_leaderboard,
    register_team_session,
    get_recent_deals,
    get_all_sessions_with_history,
)

load_personas()
for c in get_all_customers():
    init_customer_budget(c["id"], c["budget"])

mcp = FastMCP("sales-training-platform")


@mcp.tool
def list_customers() -> str:
    """列出平台上所有可用的客戶。每個客戶有不同的個性、難度和剩餘預算。"""
    customers = get_all_customers()
    for c in customers:
        c["remaining_budget"] = get_remaining_budget(c["id"])
    return json.dumps(customers, ensure_ascii=False, indent=2)


@mcp.tool
def find_customer(api_key: str, preferred_tags: str = "") -> str:
    """隨機分配一位客戶給你。可以提供偏好標籤來影響配對（但不保證）。

    Args:
        api_key: 你的 API 金鑰
        preferred_tags: 偏好的客戶標籤，逗號分隔（例如：「保守型,高資產」）。可為空字串表示完全隨機。
    """
    user = validate_key(api_key)
    if user is None:
        return json.dumps({"error": "無效的 API 金鑰"}, ensure_ascii=False)

    if preferred_tags.strip():
        tags = [t.strip() for t in preferred_tags.split(",")]
        candidates = get_customers_by_tags(tags)
    else:
        candidates = [get_customer(c["id"]) for c in get_all_customers()]

    available = [c for c in candidates if get_remaining_budget(c["id"]) > 0]

    if not available:
        return json.dumps({"error": "目前所有客戶的預算都已用完，請稍後再試"}, ensure_ascii=False)

    if preferred_tags.strip():
        customer = available[0]
    else:
        customer = random.choice(available)

    return json.dumps({
        "customer_id": customer["id"],
        "name": customer["display_name"],
        "difficulty": customer["difficulty"],
        "tags": customer.get("tags", []),
        "remaining_budget": get_remaining_budget(customer["id"]),
        "background_summary": customer["background"].strip()[:120] + "...",
        "hint": "使用 start_session 開始跟這位客戶對話",
    }, ensure_ascii=False, indent=2)


@mcp.tool
def start_session(
    customer_id: str,
    salesperson_persona: str,
    product_context: str,
    api_key: str,
    agent_name: str = "",
    team_display_name: str = "",
) -> str:
    """開始一段銷售對話。

    Args:
        customer_id: 客戶 ID（從 list_customers 或 find_customer 取得）
        salesperson_persona: 你的理專人設描述（例如：「我是一位有5年經驗的理專，擅長基金配置」）
        product_context: 你想銷售的產品或服務描述（例如：「全球股票型基金、退休規劃」）
        api_key: 你的 API 金鑰（依組別分配，例如 team-red-key）
        agent_name: 你的顯示名稱（會出現在競技場大廳上）。請取一個有個性的名字！
        team_display_name: 你們組的隊名（例如「閃電隊」）。同組請統一這個名字。沒填會用預設組名。
    """
    user = validate_key(api_key)
    if user is None:
        return json.dumps({"error": "無效的 API 金鑰"}, ensure_ascii=False)

    if not agent_name.strip():
        return json.dumps({
            "error": "請提供 agent_name 參數！這是你在競技場大廳上的顯示名稱，讓大家認得出你。例如：「小王」「理財達人Amy」「金融狗狗」都可以。",
        }, ensure_ascii=False)

    customer = get_customer(customer_id)
    if customer is None:
        return json.dumps({"error": f"找不到客戶 ID: {customer_id}"}, ensure_ascii=False)

    remaining = get_remaining_budget(customer_id)
    if remaining <= 0:
        return json.dumps({"error": "這位客戶的預算已用完，請換一位客戶"}, ensure_ascii=False)

    final_team_name = team_display_name.strip() or "未分組"
    from src.arena import derive_team_id, derive_team_color
    team_id = derive_team_id(final_team_name)
    team_color = derive_team_color(final_team_name)

    session_id = create_session(
        customer_id, salesperson_persona, product_context, api_key, agent_name,
        opening_line=customer["opening_line"],
        team_id=team_id,
        team_display_name=final_team_name,
        team_color=team_color,
    )

    if team_id:
        register_team_session(team_id, final_team_name, agent_name)

    return json.dumps({
        "session_id": session_id,
        "customer_name": customer["display_name"],
        "difficulty": customer["difficulty"],
        "opening_line": customer["opening_line"],
        "team": final_team_name,
        "hint": f"客戶已開始對話。用 send_message 回應客戶。最多 {MAX_TURNS} 輪對話。",
    }, ensure_ascii=False, indent=2)


@mcp.tool
def send_message(session_id: str, message: str) -> str:
    """向客戶發送一條訊息，並獲得客戶的回應。如果客戶決定購買，回應中會包含成交資訊。

    Args:
        session_id: 對話 session ID（從 start_session 取得）
        message: 你要對客戶說的話
    """
    session_data = get_session(session_id)
    if session_data is None:
        return json.dumps({"error": "Session 不存在或已過期"}, ensure_ascii=False)

    if session_data["status"] != "active":
        return json.dumps({"error": "此對話已結束"}, ensure_ascii=False)

    if is_turn_limit_reached(session_data):
        return json.dumps({
            "error": f"已達到最大對話輪數 ({MAX_TURNS})，請呼叫 end_session 結束對話並取得評分。",
        }, ensure_ascii=False)

    customer = get_customer(session_data["customer_id"])
    customer_response = get_customer_response(
        customer=customer,
        history=session_data["history"],
        salesperson_message=message,
    )

    updated = add_turn(session_id, message, customer_response)

    result = {
        "customer_response": customer_response,
        "turn_number": updated["turn_count"],
        "turns_remaining": MAX_TURNS - updated["turn_count"],
    }

    # If the customer's reply hints at buying (explicit marker OR natural language),
    # nudge the salesperson to wrap up. Final deal verdict is judged by the coach
    # LLM at end_session, so this is just an in-conversation hint.
    if detect_deal(customer_response):
        result["hint"] = (f"💡 {customer['display_name']} 似乎有購買意願了！"
                          f"可以呼叫 end_session 結算——成交與否、金額多少由你的表現分數決定。")

    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool
def end_session(session_id: str) -> str:
    """結束對話並取得 AI 教練的評分和改善建議。

    Args:
        session_id: 對話 session ID
    """
    session_data = get_session(session_id)
    if session_data is None:
        return json.dumps({"error": "Session 不存在或已過期"}, ensure_ascii=False)

    if len(session_data["history"]) == 0:
        return json.dumps({"error": "對話還沒開始，無法評分"}, ensure_ascii=False)

    customer = get_customer(session_data["customer_id"])

    evaluation, score, is_deal, product, offered = evaluate_session(
        customer=customer,
        history=session_data["history"],
    )

    # Coach LLM judges deal + extracts the amount the customer chose to invest.
    # The customer decides the amount based on satisfaction (no score multiplier).
    deal_result = None
    if is_deal:
        budget = get_remaining_budget(session_data["customer_id"])
        default_offer = customer.get("default_offer", 1000000)
        amount = final_deal_amount(offered, budget, default_offer)

        if amount > 0 and deduct_budget(session_data["customer_id"], amount):
            agent_name = session_data.get("agent_name") or validate_key(session_data["api_key"])["name"]
            record_deal(
                agent_name,
                session_data["customer_id"],
                product,
                amount,
                session_id,
                team_id=session_data.get("team_id", ""),
                team_display_name=session_data.get("team_display_name", ""),
            )
            capped_note = "（已達客戶剩餘預算上限）" if offered > amount and offered > 0 else ""
            deal_result = {
                "product": product,
                "amount": amount,
                "score": score,
                "message": (
                    f"🎉 成交！客戶決定投入 ${amount:,} 購買「{product}」{capped_note}\n"
                    f"   這個金額是客戶根據你的表現自己決定的——"
                    f"你的教練分數 {score} 分。想讓客戶投更多？看評分建議改進你的 agent。"
                ),
            }
        else:
            deal_result = {
                "product": product,
                "amount": 0,
                "score": score,
                "message": "客戶嘴上鬆動但最終沒有投入（金額為 0 或預算用完）。看評分找出問題。",
            }

    ended_data = end_session_db(session_id)
    transcript_path = save_transcript(ended_data, evaluation)

    remaining = get_remaining_budget(session_data["customer_id"])
    return json.dumps({
        "score": score,
        "evaluation": evaluation,
        "deal": deal_result,
        "summary": {
            "customer": customer["display_name"],
            "customer_remaining_budget": remaining,
            "total_turns": ended_data["turn_count"],
            "transcript_saved": transcript_path,
        },
    }, ensure_ascii=False, indent=2)


AUTO_MAX_TURNS = 15


@mcp.tool
def run_full_session(
    customer_id: str,
    salesperson_persona: str,
    product_context: str,
    api_key: str,
    agent_name: str = "Auto-Demo",
    max_turns: int = AUTO_MAX_TURNS,
) -> str:
    """全自動執行一場完整銷售對話（Demo/快速測試用）。

    Args:
        customer_id: 客戶 ID
        salesperson_persona: 理專人設描述
        product_context: 要銷售的產品描述
        api_key: API 金鑰
        agent_name: 顯示名稱（預設 Auto-Demo）
        max_turns: 最多對話輪數（預設 15）
    """
    user = validate_key(api_key)
    if user is None:
        return json.dumps({"error": "無效的 API 金鑰"}, ensure_ascii=False)

    customer = get_customer(customer_id)
    if customer is None:
        return json.dumps({"error": f"找不到客戶 ID: {customer_id}"}, ensure_ascii=False)

    max_turns = min(max_turns, MAX_TURNS)
    from src.arena import derive_team_id, derive_team_color
    final_team_name = "Auto-Demo"
    team_id = derive_team_id(final_team_name)
    team_color = derive_team_color(final_team_name)
    session_id = create_session(
        customer_id, salesperson_persona, product_context, api_key, agent_name,
        opening_line=customer["opening_line"],
        team_id=team_id,
        team_display_name=final_team_name,
        team_color=team_color,
    )
    if team_id:
        register_team_session(team_id, final_team_name, agent_name)
    history: list[dict] = []
    deals_made: list[dict] = []

    customer_message = customer["opening_line"]

    for turn_num in range(1, max_turns + 1):
        salesperson_response = get_salesperson_response(
            salesperson_persona=salesperson_persona,
            product_context=product_context,
            history=history,
            customer_message=customer_message,
        )

        customer_response = get_customer_response(
            customer=customer,
            history=history,
            salesperson_message=salesperson_response,
        )

        turn = {"salesperson": salesperson_response, "customer": customer_response}
        history.append(turn)
        add_turn(session_id, salesperson_response, customer_response)

        if turn_num >= 3 and should_end_conversation(history):
            break

        customer_message = customer_response

    evaluation, score, is_deal, product, offered = evaluate_session(customer=customer, history=history)

    # Coach LLM judges deal + extracts stated amount; final = stated × multiplier
    deals_made: list[dict] = []
    if is_deal:
        budget = get_remaining_budget(customer_id)
        default_offer = customer.get("default_offer", 1000000)
        amount = final_deal_amount(offered, budget, default_offer)
        if amount > 0 and deduct_budget(customer_id, amount):
            record_deal(
                agent_name or user["name"], customer_id, product, amount, session_id,
                team_id=team_id, team_display_name=final_team_name,
            )
            deals_made.append({"product": product, "amount": amount})

    ended_data = end_session_db(session_id)
    transcript_path = save_transcript(ended_data, evaluation)

    conversation_display = ""
    for i, turn in enumerate(history, 1):
        conversation_display += f"【第 {i} 輪】\n"
        conversation_display += f"理專：{turn['salesperson']}\n"
        conversation_display += f"客戶：{turn['customer']}\n\n"

    return json.dumps({
        "conversation": conversation_display,
        "score": score,
        "deals": deals_made,
        "evaluation": evaluation,
        "summary": {
            "customer": customer["display_name"],
            "difficulty": customer["difficulty"],
            "total_turns": len(history),
            "transcript_saved": transcript_path,
        },
    }, ensure_ascii=False, indent=2)


# === Web API for the arena dashboard ===

async def api_sessions(request):
    sessions = get_all_sessions_with_history()
    display = []
    for s in sessions[:50]:
        customer = get_customer(s["customer_id"])
        agent_name = s.get("agent_name", "")
        if not agent_name:
            user = validate_key(s.get("api_key", ""))
            agent_name = user["name"] if user else "Unknown"
        display.append({
            "session_id": s["session_id"],
            "agent_name": agent_name,
            "customer_name": customer["display_name"] if customer else s["customer_id"],
            "customer_id": s["customer_id"],
            "status": s["status"],
            "turn_count": s["turn_count"],
            "opening_line": s.get("opening_line", ""),
            "history": s["history"][-5:],
            "created_at": s["created_at"],
            "team_id": s.get("team_id", ""),
            "team_display_name": s.get("team_display_name", ""),
            "team_color": s.get("team_color", ""),
        })
    return JSONResponse(display)


async def api_leaderboard(request):
    # Personal leaderboard, enriched with team info if available
    # Build agent → team map from BOTH active sessions AND historical deals
    # (sessions may have been deleted by Redis TTL, but deals persist)
    agent_to_team = {}
    sessions = get_all_sessions_with_history()
    for s in sessions:
        an = s.get("agent_name", "")
        if an and an not in agent_to_team:
            agent_to_team[an] = {
                "team_id": s.get("team_id", ""),
                "team_display_name": s.get("team_display_name", ""),
                "team_color": s.get("team_color", ""),
            }

    # Fall back to deals for agents whose sessions have already expired.
    # Team color is derived from team name (hash → palette), so no key lookup needed.
    from src.arena import derive_team_color
    for d in get_recent_deals(100):
        an = d.get("agent", "")
        if an and an not in agent_to_team:
            tid = d.get("team_id", "")
            tname = d.get("team_display_name", "")
            agent_to_team[an] = {
                "team_id": tid,
                "team_display_name": tname,
                "team_color": derive_team_color(tname),
            }

    lb = get_leaderboard()
    for entry in lb:
        info = agent_to_team.get(entry["agent"], {})
        entry.update(info)
    return JSONResponse(lb)


async def api_team_leaderboard(request):
    return JSONResponse(get_team_leaderboard())


async def api_deals(request):
    from src.arena import derive_team_color
    deals = get_recent_deals(30)
    for d in deals:
        customer = get_customer(d.get("customer_id", ""))
        d["customer_name"] = customer["display_name"] if customer else d.get("customer_id", "")
        d["team_color"] = derive_team_color(d.get("team_display_name", ""))
    return JSONResponse(deals)


async def api_customers(request):
    customers = get_all_customers()
    for c in customers:
        c["remaining_budget"] = get_remaining_budget(c["id"])
    return JSONResponse(customers)


async def serve_dashboard(request):
    from pathlib import Path
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


async def serve_starter_zip(request):
    from pathlib import Path
    from starlette.responses import FileResponse
    zip_path = Path(__file__).parent / "starter" / "codex-arena.zip"
    return FileResponse(zip_path, media_type="application/zip", filename="codex-arena.zip")


async def serve_starter_tar(request):
    from pathlib import Path
    from starlette.responses import FileResponse
    tar_path = Path(__file__).parent / "starter" / "codex-arena.tar.gz"
    return FileResponse(tar_path, media_type="application/gzip", filename="codex-arena.tar.gz")


async def serve_project_summary(request):
    from pathlib import Path
    from starlette.responses import FileResponse
    md_path = Path(__file__).parent / "PROJECT_SUMMARY.md"
    return FileResponse(md_path, media_type="text/markdown; charset=utf-8", filename="PROJECT_SUMMARY.md")


app = mcp.http_app()

web_routes = [
    Route("/", serve_dashboard),
    Route("/api/sessions", api_sessions),
    Route("/api/leaderboard", api_leaderboard),
    Route("/api/team_leaderboard", api_team_leaderboard),
    Route("/api/deals", api_deals),
    Route("/api/customers", api_customers),
    Route("/download/codex-arena.zip", serve_starter_zip),
    Route("/download/codex-arena.tar.gz", serve_starter_tar),
    Route("/download/PROJECT_SUMMARY.md", serve_project_summary),
]

for route in web_routes:
    app.routes.insert(0, route)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=MCP_PORT)
