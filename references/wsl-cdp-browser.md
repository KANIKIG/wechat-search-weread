# WSL 环境下连接 Windows CDP 浏览器

如果你是 WSL 用户，需要通过以下步骤让 agent-browser 连接到 Windows 上的 Edge 浏览器。

## 为什么需要这个

WSL2 有独立的网络命名空间，Windows 上的 Chrome/Edge CDP 默认绑定 `127.0.0.1`，WSL 无法直接访问。`--remote-debugging-address=0.0.0.0` 在 Chrome/Edge 上均无效。

## 步骤

### 1. 启动 Edge CDP 浏览器

```bash
# 先关掉已有的 Edge
/mnt/c/Windows/System32/taskkill.exe /F /IM msedge.exe 2>/dev/null; sleep 2

# 用独立 user-data-dir 启动（否则会被已有 Edge 实例拦截）
"/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
  --remote-debugging-port=9222 \
  --user-data-dir="C:/Users/gdc3489/AppData/Local/Temp/edge_debug" \
  --no-first-run --no-default-browser-check about:blank &

sleep 5
```

### 2. 配置端口转发

```bash
# 端口转发：0.0.0.0:9223 → 127.0.0.1:9222
/mnt/c/Windows/System32/netsh.exe interface portproxy add v4tov4 \
  listenport=9223 listenaddress=0.0.0.0 \
  connectport=9222 connectaddress=127.0.0.1

# Windows 防火墙放行（必须！否则 WSL→Windows 流量被拦截）
/mnt/c/Windows/System32/netsh.exe advfirewall firewall add rule \
  name="WSL CDP Proxy 9223" dir=in action=allow protocol=tcp localport=9223
```

### 3. 获取连接地址并验证

```bash
WINDOWS_IP=$(ip route | grep default | awk '{print $3}')
curl -s "http://${WINDOWS_IP}:9223/json/version" | python3 -c "import sys,json; print(json.load(sys.stdin).get('Browser','FAIL'))"
# 输出：Edge/xxx 即成功
```

### 4. 连接 agent-browser

```bash
WS_URL=$(curl -s "http://${WINDOWS_IP}:9223/json/version" | python3 -c "import sys,json; print(json.load(sys.stdin)['webSocketDebuggerUrl'])")
agent-browser --cdp "$WS_URL" goto "https://weread.qq.com/"
```

## 注意事项

- **必须用独立 `--user-data-dir`**，否则已有 Edge 实例会拦截启动，`--remote-debugging-port` 被丢弃
- **用 `goto` 不用 `open`**：`agent-browser --cdp <WS_URL> open` 会尝试 auto-launch 冲突，用 `goto`
- **端口转发规则重启后持久**，只需运行一次
- **Windows IP 会变**（DHCP），每次用 `ip route | grep default | awk '{print $3}'` 获取
