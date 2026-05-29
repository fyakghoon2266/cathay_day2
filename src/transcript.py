import json
import time
from pathlib import Path

_TRANSCRIPT_DIR = Path(__file__).parent.parent / "transcripts"
_TRANSCRIPT_DIR.mkdir(exist_ok=True)


def save_transcript(session_data: dict, evaluation: str) -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    customer_id = session_data["customer_id"]
    session_id = session_data["session_id"][:8]
    filename = f"{ts}_{customer_id}_{session_id}.json"

    record = {
        "session_id": session_data["session_id"],
        "customer_id": customer_id,
        "salesperson_persona": session_data["salesperson_persona"],
        "product_context": session_data["product_context"],
        "turn_count": session_data["turn_count"],
        "history": session_data["history"],
        "evaluation": evaluation,
        "created_at": session_data["created_at"],
        "ended_at": session_data.get("ended_at", time.time()),
    }

    filepath = _TRANSCRIPT_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    return str(filepath)
