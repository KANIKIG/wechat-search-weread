# WSL 环境下连接 Windows CDP 浏览器

WSL 用户需要通过以下步骤让 agent-browser 连接到 Windows 上的 CDP 浏览器（Edge 或 Chrome）。

## 为什么需要这个

WSL2 有独立的网络命名空间，Windows 上的 CDP 默认绑定 `127.0.0.1`，WSL 无法直接访问。

## 步骤

### 1. 启动 CDP 浏览器

**Edge**（推荐，Windows 自带）：
```bash
# 先关掉已有的实例
/mnt/c/Windows/System32/taskkill.exe /F /IM msedge.exe 2>/dev/null; sleep 2

# 用独立 user-data-dir 启动
"/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
  --remote-debugging-port=9222 \
  --user-data-dir="C:/Users/gdc3489/AppData/Local/Temp/edge_debug" \
  --no-first-run --no-default-browser-check about:blank &
sleep 5
```

**Chrome**（备选，需自行安装）：
```bash
"/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" \
  --remote-debugging-port=9222 \
  --user-data-dir=C:/Users/gdc3489/AppData/Local/Temp/chrome_debug \
  --no-first-run about:blank &
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
# 输出浏览器名称即成功
```

### 4. 连接 agent-browser

> ⚠️ `agent-browser --cdp <WS_URL>` 在 WSL 端口代理环境下不可用（报 404）。**改用两步法：先 `connect`，再正常使用命令。**

```bash
WINDOWS_IP=$(ip route | grep default | awk '{print $3}')

# Step 1: connect（建立会话）
agent-browser connect "http://${WINDOWS_IP}:9223"

# Step 2: 正常使用（无需 --cdp 前缀）
agent-browser goto "https://weread.qq.com/"
agent-browser snapshot
```

> 💡 `connect` 之后所有 agent-browser 命令都不需要 `--cdp` 前缀，会话级保持连接。如果连接断开（如浏览器重启），重新 `connect` 即可。

## 注意事项

- **必须用独立 `--user-data-dir`**，否则已有浏览器实例会拦截启动
- **用 `connect` 不用 `--cdp`**：`agent-browser --cdp <port>` 在当前版本（0.27.0）下对 WSL 端口代理返回 404。先用 `connect "http://<IP>:9223"`，之后命令不加任何 CDP flag
- **用 `goto` 不用 `open`**：`agent-browser open` 会尝试 auto-launch 冲突，用 `goto`
- **端口转发规则重启后持久**，只需运行一次
- **Windows IP 会变**（DHCP），每次用 `ip route | grep default | awk '{print $3}'` 获取
