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
    key = f"budget:{customer_id}"
    val = _redis.get(key)
    if val is None:
        # Self-heal: budget key missing (e.g. Redis was flushed/restarted while
        # the server kept running). Re-seed from the persona's original budget
        # so the arena keeps working without needing a server restart.
        from .personas_loader import get_customer
        c = get_customer(customer_id)
        if c and c.get("budget"):
            _redis.set(key, c["budget"])
            return int(c["budget"])
        return 0
    return int(val)


# Atomic check-and-deduct: avoids race conditions when many agents (e.g. 60
# sub-agents) try to close on the same customer simultaneously. Runs entirely
# inside Redis so the read + compare + decrement can't interleave.
_DEDUCT_LUA = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local amount = tonumber(ARGV[1])
if amount > current then
    return -1
end
redis.call('DECRBY', KEYS[1], amount)
return current - amount
"""
_deduct_script = _redis.register_script(_DEDUCT_LUA)


def deduct_budget(customer_id: str, amount: int) -> bool:
    """Atomically deduct `amount` from the customer's budget.
    Returns True if deducted, False if insufficient budget."""
    if amount <= 0:
        return False
    result = _deduct_script(keys=[f"budget:{customer_id}"], args=[amount])
    return int(result) >= 0


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


# A single deal can never take more than this fraction of the customer's
# ORIGINAL total wealth — keeps one conversation from draining a customer and
# stops over-large single closes.
MAX_DEAL_FRACTION = 0.15


def final_deal_amount(customer_offered: int, remaining_budget: int,
                      default_offer: int, total_budget: int) -> int:
    """The deal amount is what the customer said they'd invest, capped by:
      (a) 15% of the customer's ORIGINAL total wealth (per-deal ceiling)
      (b) the customer's remaining budget (can't spend what's gone)

    The customer agent decides the base amount via its amount_decision ladder
    (no score multiplier). We only clamp and round here.

    - customer_offered: amount the customer named; -1 if agreed but gave no figure
    - remaining_budget: how much the customer still has (hard cap)
    - default_offer: persona fallback when no figure was named
    - total_budget: the customer's original full budget (for the 15% ceiling)
    """
    base = customer_offered if customer_offered and customer_offered > 0 else default_offer
    per_deal_cap = int(total_budget * MAX_DEAL_FRACTION)
    amount = min(base, per_deal_cap, remaining_budget)
    amount = (amount // 10000) * 10000       # round to nearest 萬
    return amount


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
