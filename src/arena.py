import hashlib
import json
import re
import time
import redis
from .config import REDIS_URL

_redis = redis.from_url(REDIS_URL, decode_responses=True)

# Primary pattern: complete [成交:產品名:金額]
DEAL_PATTERN = re.compile(r"\[成交[:：](.+?)[:：](\d[\d,，]*)\]?")
# Fallback: customer wrote [成交:產品名:金額 but truncated by max_tokens
DEAL_PATTERN_TRUNCATED = re.compile(r"\[成交[:：](.+?)[:：](\d[\d,，]*)\s*$")

# Curated palette of distinguishable, demo-friendly colors
TEAM_COLOR_PALETTE = [
    "#e63946",  # red
    "#1d6fb8",  # blue
    "#2a9d4f",  # green
    "#f4a300",  # yellow/amber
    "#8e44ad",  # purple
    "#e67e22",  # orange
    "#16a085",  # teal
    "#c2185b",  # pink/magenta
    "#5d4037",  # brown
    "#455a64",  # blue-grey
]


def normalize_team_name(name: str) -> str:
    """Trim whitespace; same name with surrounding spaces should collapse to same team."""
    return (name or "").strip()


def derive_team_id(team_display_name: str) -> str:
    """Stable ID for a team derived from its display name.
    Uses MD5 prefix so the same name always maps to the same id."""
    norm = normalize_team_name(team_display_name)
    if not norm:
        return ""
    return "team_" + hashlib.md5(norm.encode("utf-8")).hexdigest()[:10]


def derive_team_color(team_display_name: str) -> str:
    """Hash team name to one of the palette colors. Same name → same color."""
    norm = normalize_team_name(team_display_name)
    if not norm:
        return "#71767b"
    h = int(hashlib.md5(norm.encode("utf-8")).hexdigest(), 16)
    return TEAM_COLOR_PALETTE[h % len(TEAM_COLOR_PALETTE)]


def init_customer_budget(customer_id: str, total_budget: int):
    key = f"budget:{customer_id}"
    if not _redis.exists(key):
        _redis.set(key, total_budget)


def get_remaining_budget(customer_id: str) -> int:
    val = _redis.get(f"budget:{customer_id}")
    return int(val) if val else 0


def deduct_budget(customer_id: str, amount: int) -> bool:
    key = f"budget:{customer_id}"
    current = int(_redis.get(key) or 0)
    if amount > current:
        return False
    _redis.decrby(key, amount)
    return True


def detect_deal(customer_response: str) -> str | None:
    """Detect a deal intent in the customer's response.

    Returns the product name if the customer signalled intent to buy
    (the LLM's quoted amount is ignored — the final amount is computed
    from the coach's score at end_session). Returns None if no deal.
    """
    for pattern in (DEAL_PATTERN, DEAL_PATTERN_TRUNCATED):
        match = pattern.search(customer_response)
        if match:
            product = match.group(1).strip()
            if product:
                return product
    return None


def performance_multiplier(score: int) -> float:
    """How much the customer adjusts their stated investment based on the
    salesperson's performance score (0-100).

    90-100 → 1.5-2.0x  (impressed, invests more than first said)
    70-89  → 1.0-1.3x  (satisfied, sticks to / slightly above stated)
    50-69  → 0.6-0.9x  (hesitant, invests less than stated)
    < 50   → 0         (walks away)
    """
    if score < 50:
        return 0.0
    if score >= 90:
        return 1.5 + (score - 90) / 10 * 0.5    # 1.5 → 2.0
    if score >= 70:
        return 1.0 + (score - 70) / 20 * 0.3    # 1.0 → 1.3
    return 0.6 + (score - 50) / 20 * 0.3        # 0.6 → 0.9


def final_deal_amount(customer_offered: int, score: int, budget: int, default_offer: int) -> tuple[int, float]:
    """Compute the final deal amount = (customer's stated amount) × performance multiplier.

    - customer_offered: amount the customer named in conversation; -1 if unspecified
    - score: coach score, drives the multiplier
    - budget: customer's remaining budget (hard cap)
    - default_offer: persona fallback when the customer didn't name a figure

    Returns (final_amount, multiplier).
    """
    mult = performance_multiplier(score)
    if mult == 0:
        return 0, 0.0
    base = customer_offered if customer_offered and customer_offered > 0 else default_offer
    amount = int(base * mult)
    amount = min(amount, budget)               # never exceed remaining budget
    amount = (amount // 10000) * 10000          # round to nearest 萬
    return amount, mult


def record_deal(
    agent_name: str,
    customer_id: str,
    product: str,
    amount: int,
    session_id: str,
    team_id: str = "",
    team_display_name: str = "",
):
    deal = {
        "agent": agent_name,
        "customer_id": customer_id,
        "product": product,
        "amount": amount,
        "session_id": session_id,
        "team_id": team_id,
        "team_display_name": team_display_name,
        "timestamp": time.time(),
    }
    _redis.lpush("deals", json.dumps(deal, ensure_ascii=False))
    _redis.zincrby("leaderboard", amount, agent_name)
    if team_id:
        _redis.zincrby("leaderboard:team", amount, team_id)
        # Also track member count + display name
        _redis.sadd(f"team:{team_id}:members", agent_name)
        if team_display_name:
            _redis.set(f"team:{team_id}:display_name", team_display_name)


def get_leaderboard(top_n: int = 20) -> list[dict]:
    entries = _redis.zrevrange("leaderboard", 0, top_n - 1, withscores=True)
    return [{"agent": name, "total_amount": int(score)} for name, score in entries]


def get_team_leaderboard(top_n: int = 10) -> list[dict]:
    entries = _redis.zrevrange("leaderboard:team", 0, top_n - 1, withscores=True)
    result = []
    for team_id, score in entries:
        display_name = _redis.get(f"team:{team_id}:display_name") or team_id
        member_count = _redis.scard(f"team:{team_id}:members")
        result.append({
            "team_id": team_id,
            "team_display_name": display_name,
            "total_amount": int(score),
            "member_count": member_count,
        })
    return result


def register_team_session(team_id: str, team_display_name: str, agent_name: str):
    """Track that an agent is on a team, even if they haven't deal yet."""
    if not team_id:
        return
    _redis.sadd(f"team:{team_id}:members", agent_name)
    if team_display_name:
        _redis.set(f"team:{team_id}:display_name", team_display_name)
    # Make sure team appears in leaderboard with 0 if not yet
    if _redis.zscore("leaderboard:team", team_id) is None:
        _redis.zadd("leaderboard:team", {team_id: 0})


def get_recent_deals(count: int = 20) -> list[dict]:
    raw = _redis.lrange("deals", 0, count - 1)
    return [json.loads(d) for d in raw]


def get_active_sessions() -> list[dict]:
    keys = _redis.keys("session:*")
    sessions = []
    for key in keys:
        raw = _redis.get(key)
        if raw:
            data = json.loads(raw)
            if data.get("status") == "active":
                sessions.append(data)
    return sessions


def get_all_sessions_with_history() -> list[dict]:
    keys = _redis.keys("session:*")
    sessions = []
    for key in keys:
        raw = _redis.get(key)
        if raw:
            sessions.append(json.loads(raw))
    sessions.sort(key=lambda s: s.get("created_at", 0), reverse=True)
    return sessions
