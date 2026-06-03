import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
# 評分/成交判定用最強模型（Opus 4.8），避免把「未來再說」誤判成「現在成交」
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-opus-4-8")
BEDROCK_MODEL_ID_CHEAP = os.getenv("BEDROCK_MODEL_ID_CHEAP", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "12"))
MAX_TURNS = int(os.getenv("MAX_TURNS", "10"))
MCP_PORT = int(os.getenv("MCP_PORT", "8765"))
