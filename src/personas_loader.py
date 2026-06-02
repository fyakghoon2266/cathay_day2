import yaml
from pathlib import Path

_PERSONAS_FILE = Path(__file__).parent.parent / "personas.yaml"
_personas: dict[str, dict] = {}


def load_personas():
    global _personas
    with open(_PERSONAS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    _personas = {c["id"]: c for c in data["customers"]}


def get_all_customers() -> list[dict]:
    return [
        {
            "id": c["id"],
            "name": c["display_name"],
            "difficulty": c["difficulty"],
            "personality_inspiration": c["personality_inspiration"],
            "tags": c.get("tags", []),
            "budget": c.get("budget", 0),
            "idle_quotes": c.get("idle_quotes", []),
            # New 4-dimension fields surfaced to the dashboard
            "product_direction_hint": c.get("product_direction_hint", ""),
            "interest_hook": c.get("interest_hook", ""),
            "background_summary": c["background"].strip()[:120] + "...",
        }
        for c in _personas.values()
    ]


def get_customer(customer_id: str) -> dict | None:
    return _personas.get(customer_id)


def get_customers_by_tags(preferred_tags: list[str]) -> list[dict]:
    scored = []
    for c in _personas.values():
        overlap = len(set(preferred_tags) & set(c.get("tags", [])))
        scored.append((overlap, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored]


load_personas()
