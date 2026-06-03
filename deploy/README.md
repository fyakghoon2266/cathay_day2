# 部署說明（Deployment）

正式環境跑在 AWS EC2，前面有 nginx 反向代理，對外網域是
`https://agent-market.cathayds-poc.com`。Server 由 systemd 託管，會在崩潰或
機器重開機時自動重啟。

```
使用者 Codex ──HTTPS──> nginx (443) ──> uvicorn/server.py (127.0.0.1:8765)
                                              │
                                              ├── Redis (docker, :6379)
                                              └── AWS Bedrock (us-west-2)
```

## 元件

| 元件 | 說明 |
|---|---|
| `server.py` | MCP server + Web API，跑在 8765，由 systemd 管理 |
| Redis | `docker run codex-redis`，存 session / 排行榜 / 預算 |
| nginx | 把 443 的 `agent-market.cathayds-poc.com` 轉到 127.0.0.1:8765（需開 SSE，見下方）|
| systemd | `codex-arena.service` 託管 server，崩潰自動重啟 |

## 安裝 systemd service

```bash
sudo cp deploy/codex-arena.service /etc/systemd/system/codex-arena.service
sudo systemctl daemon-reload
sudo systemctl enable codex-arena    # 開機自啟
sudo systemctl start codex-arena
```

## 日常操作

```bash
# 看狀態 / 是否在跑
sudo systemctl status codex-arena
sudo systemctl is-active codex-arena

# 改了程式碼後重啟
sudo systemctl restart codex-arena

# 看 log
tail -f /home/ubuntu/codex-server/server.log

# 重置競技場（清空對話/排行榜/成交，預算重新初始化）
docker exec codex-redis redis-cli FLUSHDB && sudo systemctl restart codex-arena
```

> ⚠️ 由 systemd 託管後，**不要再用 `pkill` 或 `nohup` 手動重啟** ——
> pkill 掉 systemd 會立刻又拉起來。一律用 `systemctl restart`。

## nginx 重點：SSE 必須關 buffering

MCP 走 SSE 串流，nginx 預設的 proxy buffering 會把串流卡住導致 MCP 連線無回應。
對應的 `location /mcp`（或整個 server）需要：

```nginx
location / {
    proxy_pass http://127.0.0.1:8765;
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_buffering off;          # 關鍵：SSE 不能 buffer
    proxy_read_timeout 300s;      # 對話較長，拉長 timeout
    chunked_transfer_encoding off;
}
```

（目前線上 nginx 已設定正確，SSE tools/call 實測通過。）

## 自動重啟驗證

```bash
# kill 掉 server，3 秒內 systemd 會自動拉起新的 process
sudo kill -9 $(pgrep -f server.py); sleep 4; sudo systemctl is-active codex-arena
```

## 壓力測試

`loadtest.py` 模擬並發 MCP client（見 repo 根目錄）。實測 60 並發全數成功、
原子扣款正確、server 穩定。

```bash
.venv/bin/python loadtest.py 20 40 60
```
