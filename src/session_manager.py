import json
import uuid
import time
import redis
from .config import REDIS_URL, SESSION_TTL_HOURS, MAX_TURNS

_redis = redis.from_url(REDIS_URL, decode_responses=True)
_TTL = SESSION_TTL_HOURS * 3600


def create_session(
    customer_id: str,
    salesperson_persona: str,
    product_context: str,
    api_key: str,
    agent_name: str = "",
    opening_line: str = "",
    team_id: str = "",
    team_display_name: str = "",
    team_color: str = "",
) -> str:
    session_id = str(uuid.uuid4())
    data = {
        "session_id": session_id,
        "customer_id": customer_id,
        "salesperson_persona": salesperson_persona,
        "product_context": product_context,
        "api_key": api_key,
        "agent_name": agent_name,
        "opening_line": opening_line,
        "team_id": team_id,
        "team_display_name": team_display_name,
        "team_color": team_color,
        "history": [],
        "turn_count": 0,
        "created_at": time.time(),
        "status": "active",
    }
    _redis.setex(f"session:{session_id}", _TTL, json.dumps(data, ensure_ascii=False))
    # Index by created_at so listing never needs a blocking `KEYS session:*` scan.
    # (Ended/expired entries are pruned lazily on read in arena.get_all_sessions.)
    _redis.zadd("session_index", {session_id: data["created_at"]})
    return session_id


def get_session(session_id: str) -> dict | None:
    raw = _redis.get(f"session:{session_id}")
    if raw is None:
        return None
    return json.loads(raw)


def add_turn(session_id: str, salesperson_msg: str, customer_msg: str) -> dict:
    data = get_session(session_id)
    if data is None:
        raise ValueError("Session not found or expired")

    turn = {"salesperson": salesperson_msg, "customer": customer_msg}
    data["history"].append(turn)
    data["turn_count"] += 1

    _redis.setex(f"session:{session_id}", _TTL, json.dumps(data, ensure_ascii=False))
    return data


def set_deal_intent(session_id: str, product: str) -> dict:
    """Flag that the customer signalled intent to buy `product`.
    The final amount is decided at end_session based on the coach score."""
    data = get_session(session_id)
    if data is None:
        raise ValueError("Session not found or expired")
    data["deal_intent_product"] = product
    _redis.setex(f"session:{session_id}", _TTL, json.dumps(data, ensure_ascii=False))
    return data


def end_session(session_id: str) -> dict:
    data = get_session(session_id)
    if data is None:
        raise ValueError("Session not found or expired")
    data["status"] = "ended"
    data["ended_at"] = time.time()
    _redis.setex(f"session:{session_id}", _TTL, json.dumps(data, ensure_ascii=False))
    return data


def is_turn_limit_reached(data: dict) -> bool:
    return data["turn_count"] >= MAX_TURNS
