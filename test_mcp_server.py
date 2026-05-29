import json
import time
from fastmcp import FastMCP

mcp = FastMCP("codex-platform-test")


@mcp.tool
def ping() -> str:
    return "pong"


@mcp.tool
def echo(text: str) -> str:
    return f"echo: {text}"


def _pretty(raw: bytes) -> str:
    if not raw:
        return "<empty>"
    text = raw.decode("utf-8", errors="replace")
    if text.startswith("event:"):
        out = []
        for line in text.splitlines():
            if line.startswith("data: "):
                payload = line[6:]
                try:
                    out.append(json.dumps(json.loads(payload), ensure_ascii=False, indent=2))
                except Exception:
                    out.append(payload)
        return "\n".join(out) if out else text
    try:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    except Exception:
        return text


def body_log_middleware(app):
    async def wrapped(scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/mcp" or scope.get("method") != "POST":
            await app(scope, receive, send)
            return

        ts = time.strftime("%H:%M:%S")
        client = scope.get("client")
        client_str = f"{client[0]}:{client[1]}" if client else "?"

        # Buffer the full request body so we can log it AND replay it to the app
        chunks: list[bytes] = []
        more = True
        while more:
            msg = await receive()
            if msg["type"] == "http.request":
                chunks.append(msg.get("body", b""))
                more = msg.get("more_body", False)
            else:
                more = False
        full_body = b"".join(chunks)

        print(f"\n========== [{ts}] REQUEST from {client_str} ==========", flush=True)
        print(_pretty(full_body), flush=True)

        replayed = {"done": False}

        async def replay_receive():
            if not replayed["done"]:
                replayed["done"] = True
                return {"type": "http.request", "body": full_body, "more_body": False}
            # After body is delivered, fall back to the real receive so the
            # underlying SSE handler can observe http.disconnect events.
            return await receive()

        status_holder = {"code": 0}

        async def wrapped_send(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                print(f"---------- [{ts}] RESPONSE status {message['status']} (body streamed, not captured) ----------", flush=True)
                print("=" * 60, flush=True)
            await send(message)

        await app(scope, replay_receive, wrapped_send)

    return wrapped


app = mcp.http_app()
app = body_log_middleware(app)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
