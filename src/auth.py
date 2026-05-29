import yaml
from pathlib import Path

_KEYS_FILE = Path(__file__).parent.parent / "api_keys.yaml"
_keys: dict[str, dict] = {}


def load_keys():
    global _keys
    with open(_KEYS_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    _keys = data.get("keys", {})


def validate_key(key: str) -> dict | None:
    return _keys.get(key)


load_keys()
