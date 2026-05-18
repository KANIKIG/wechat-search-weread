# 完整操作流程

> 主 SKILL.md 的扩展，包含每个 Step 的完整命令和代码。

## 前提

- agent-browser 已安装并连接（WSL: `agent-browser connect "http://<IP>:9223"`）
- 微信读书已登录

> ⚠️ **黄金法则**：每一步操作后都等 6-10 秒！页面元素需要时间加载。
> ⚠️ **长滚动（>3 轮）必须用前台 terminal + 长 timeout（600s）**，不要用 background 进程。

---

## Step 1: 启动浏览器

**非WSL**：跳过，agent-browser 自动管理浏览器。

**WSL 用户**：参考 [wsl-cdp-browser.md](wsl-cdp-browser.md) 启动 Edge CDP 并配置端口转发。

验证连接：`agent-browser get cdp-url`（非WSL）或 `curl http://<IP>:9223/json/version`（WSL）

---

## Step 2: 登录微信读书（统一用扫码！）

### 2.0 清除旧登录态（可选，cookie 残留时）

微信读书的认证 cookie 是 httpOnly 的，需用 CDP `Storage.clearCookies`（**page 级别** WebSocket）：

```python
import asyncio, json, subprocess, websockets

# 获取 CDP browser WebSocket URL
# 非WSL: result = subprocess.run(['agent-browser', 'get', 'cdp-url'], capture_output=True, text=True)
# WSL:   result = subprocess.run(['curl', '-s', 'http://WINDOWS_IP:9223/json/version'], capture_output=True, text=True)
#         version['webSocketDebuggerUrl']

# 获取 weread 页面的 page-level WS URL
result = subprocess.run(['curl', '-s', '<browser_ws_url替换为/json>'],
                       capture_output=True, text=True)
targets = json.loads(result.stdout)
weread_ws = None
for t in targets:
    if t['type'] == 'page' and 'weread' in t.get('url', ''):
        weread_ws = t['webSocketDebuggerUrl']
        break

async def clear():
    async with websockets.connect(weread_ws, max_size=2**24) as ws:
        await ws.send(json.dumps({'id': 1, 'method': 'Storage.clearCookies', 'params': {}}))
        resp = await asyncio.wait_for(ws.recv(), timeout=5)
        print(resp)

asyncio.run(clear())
```

> `Network.clearBrowserCookies` 在此 Edge 版本返回 `-32601`，只用 `Storage.clearCookies`。

清除后 reload 页面确认"登录"链接出现。

### 2.1 导航并点击登录

```bash
agent-browser goto "https://weread.qq.com/"
sleep 8
```

触发登录弹窗（优先用 eval）：

```bash
# ✅ 方法1（推荐）：eval 触发
agent-browser eval "document.querySelectorAll('a').forEach(a => { if (a.textContent.includes('登录')) a.click(); })"
sleep 6

# ⚠️ 方法2（备选）：agent-browser click — 经常无效
# agent-browser snapshot | grep -i 登录
# agent-browser click <登录的ref>
# sleep 6
```

### 2.2 QR 码提取（默认「刷新后提取」）

> 首次 eval 触发的 QR 经常是旧缓存的。必须：关闭弹窗 → 重新触发 → 提取。

**必须用一个 terminal() 调用跑完 Step A-E！** 不要拆分。

```bash
# Step A: eval 触发第一次登录（仅用于唤起弹窗，5s 足够）
agent-browser eval "document.querySelectorAll('a').forEach(a => { if (a.textContent.includes('登录')) a.click(); })"
sleep 5

# Step B: 关闭弹窗（丢弃旧 QR）
agent-browser eval "var m=document.querySelector('.mask,.dialog_mask,.wr_overlay');if(m)m.click();'closed'"
sleep 2

# Step C: 重新触发登录（拿到新鲜 QR，6s 即可）
agent-browser eval "document.querySelectorAll('a').forEach(a => { if (a.textContent.includes('登录')) a.click(); })"
sleep 6

# Step D: 一键提取 QR（移除 iframe + 提取 src）
agent-browser eval "
(function() {
  const iframes = document.querySelectorAll('iframe');
  iframes.forEach(f => f.remove());
  const imgs = document.querySelectorAll('img');
  for (const img of imgs) {
    if (img.width > 100 && img.height > 100) return img.src;
  }
  return '';
})()" > /tmp/qr_url.txt

# Step E: 解析并下载 QR → 立即发码给用户
python3 -c "
import json, base64, os
with open('/tmp/qr_url.txt') as f:
    raw = f.read().strip()
src = json.loads(raw)
if not src:
    print('ERROR: no QR image found')
    exit(1)
if src.startswith('data:image'):
    b64 = src.split(',', 1)[1]
    b64 += '=' * (4 - len(b64) % 4) if len(b64) % 4 else ''
    with open('/tmp/weread_qr.png', 'wb') as f:
        f.write(base64.b64decode(b64))
else:
    import subprocess; subprocess.run(['curl', '-s', '-o', '/tmp/weread_qr.png', src])
print(f'QR OK: {os.path.getsize(\"/tmp/weread_qr.png\")} bytes')
"
# 整个 block 结束后立刻在回复里发 MEDIA:/tmp/weread_qr.png
```

**如果 QR 仍失效（极少情况）：** 重复 Step B-D。如果登录弹窗完全消失，重新 goto + 触发：

```bash
agent-browser goto "https://weread.qq.com/"
sleep 6
agent-browser eval "document.querySelectorAll('a').forEach(a => { if (a.textContent.includes('登录')) a.click(); })"
sleep 6
# 再次一键提取
```

**验证登录：**

```bash
agent-browser goto "https://weread.qq.com/"
sleep 6
agent-browser snapshot | grep -i "我的书架\|继续阅读"
```

**登录成功后清理临时文件：**

```bash
rm -f /tmp/weread_qr.png /tmp/qr_url.txt
```

---

## Step 3: 搜索 + 大批量滚动加载

> 🔴 **铁律：weread.qq.com 标签页绝对不能关！绝对不能离开！**
> 🔴 **滚动必须用 agent-browser 的 eval 执行，Python page WS 的 Runtime.evaluate 不会触发 XHR。**

### 3.1 导航到搜索页 + 保持 weread session

```bash
# A. agent-browser goto 搜索页
agent-browser goto \
  "https://search.weixin.qq.com/cgi-bin/newsearchweb/userclientjump?path=page/search/weread&query=URL编码关键词&platform=pc"
sleep 8
agent-browser eval "document.querySelectorAll('.search_list_item').length"

# B. 保持 weread 标签页活跃
# 获取 browser WS URL（非WSL: agent-browser get cdp-url，WSL: curl http://IP:9223/json/version）
python3 -c "
import asyncio, json, websockets
bw = '<BROWSER_WS_URL>'
async def create():
    async with websockets.connect(bw, max_size=2**24) as ws:
        await ws.send(json.dumps({'id':1,'method':'Target.createTarget','params':{'url':'https://weread.qq.com/'}}))
        print(await asyncio.wait_for(ws.recv(), timeout=10))
asyncio.run(create())
"
sleep 5

# C. agent-browser 重新 goto 搜索页
agent-browser goto \
  "https://search.weixin.qq.com/cgi-bin/newsearchweb/userclientjump?path=page/search/weread&query=URL编码关键词&platform=pc"
sleep 8
agent-browser eval "document.querySelectorAll('.search_list_item').length"
# → 初始 15 篇
```

### 3.2 滚动加载（默认滚到「暂无更多内容」，500 条封顶）

```bash
# 每轮 = 3 次 scrollTo + 2s 间隔 + 3s 渲染等待。每轮新增 ~45 篇。
PREV=""; PREV2=""
for r in $(seq 1 20); do
  for j in 1 2 3; do
    agent-browser eval "window.scrollTo(0, document.body.scrollHeight)" > /dev/null 2>&1
    sleep 2
  done
  sleep 3
  C=$(agent-browser eval "document.querySelectorAll('.search_list_item').length" 2>/dev/null)
  echo "R$r: $C"
  # 超过 500 封顶
  if [ "$C" -gt 500 ] 2>/dev/null; then
    echo "HIT 500 cap, stopping"
    break
  fi
  # 检查"暂无更多内容"
  NOMORE=$(agent-browser eval "document.body.textContent.includes('暂无更多内容')" 2>/dev/null)
  if [ "$NOMORE" = "true" ]; then
    echo "HIT 暂无更多内容 at $C, stopping"
    break
  fi
  # 连续 3 轮不变（兜底）
  if [ "$C" = "$PREV" ] && [ "$C" = "$PREV2" ]; then
    echo "PLATEAU at $C, stopping"
    break
  fi
  PREV2=$PREV; PREV=$C
done
```

> 典型增长曲线：R1→60, R2→105, R3→150, R4→195, R5→240, R6→258（然后持平）。

如果两轮后数量不变（始终 15 篇）：① weread session 丢失 ② 用了 Python page WS 做滚动。

---

## Step 4: 提取文章数据 + URL

### 4.1 批量采集文章元数据

```bash
agent-browser eval "
(() => {
    const arts = [];
    document.querySelectorAll('.search_list_item').forEach((item, i) => {
        const t = item.querySelector('.article__title-text');
        const d = item.querySelector('.article__desc');
        const s = item.querySelector('.source__title');
        const dt = item.querySelector('.source__text.date');
        arts.push({
            idx: i,
            title: (t?.textContent || '').trim(),
            desc: (d?.textContent || '').trim().substring(0,200),
            source: (s?.textContent || '').trim(),
            date: (dt?.textContent || '').trim(),
            dataId: item.getAttribute('data-id') || ''
        });
    });
    return JSON.stringify(arts);
})()" > /tmp/arts.json
```

> `agent-browser eval` 返回的字符串被双重引号包裹（`"[...]"`），解析需 `json.loads(json.loads(raw))`。

### 4.2 筛选目标文章

用 Python 解析日期，筛选近一周（或用户指定的时间范围）：

```python
def parse_date(date_str):
    now = datetime.now()
    if '小时前' in date_str:
        h = int(re.search(r'(\d+)', date_str).group(1))
        return now - timedelta(hours=h)
    elif '分钟前' in date_str:
        m = int(re.search(r'(\d+)', date_str).group(1))
        return now - timedelta(minutes=m)
    elif '天前' in date_str:
        d = int(re.search(r'(\d+)', date_str).group(1))
        return now - timedelta(days=d)
    elif re.match(r'\d{4}-\d{2}-\d{2}', date_str):
        return datetime.strptime(date_str[:10], '%Y-%m-%d')
    return None
```

### 4.3 获取文章 URL（execute_code 中执行）

用 execute_code + Python + websockets，连搜索页 page-level CDP WebSocket，一次 Runtime.evaluate 批量完成。

获取 CDP WebSocket URL：
- 非WSL：`agent-browser get cdp-url` 得浏览器级 WS → 访问 `/json` 获取 page targets
- WSL：`curl -s "http://$WINDOWS_IP:9223/json"` 获取 page targets

核心 JS（async + await sleep 防竞态）：

```js
(async function() {
    var sleep = ms => new Promise(r => setTimeout(r, ms));
    var items = document.querySelectorAll('.search_list_item');
    var orig = window.open;
    for (var i = 0; i < targets.length; i++) {
        var captured = '';
        window.open = function(u) { captured = u; };
        items[targets[i]].scrollIntoView({block: 'center', behavior: 'instant'});
        items[targets[i]].click();
        await sleep(50);
        results.push({idx: targets[i], url: captured});
    }
    window.open = orig;
    return JSON.stringify(results);
})()
```

关键点：
- 点击 `.search_list_item`（卡片 DIV），不是 `.article__title-text`
- 拦截 `window.open` 返回 null，不弹新标签页
- 必须 async function + `await sleep(50)` + `awaitPromise: true`

完整提取模板见 [extraction-pattern.md](extraction-pattern.md)。

### 4.4 输出格式

**严禁从 execute_code 控制台输出复制 URL。** 强制从 `/tmp/urls.json` 读取：

```bash
python3 -c "
import json
with open('/tmp/urls.json') as f:
    data = json.load(f)
total = len(data)
succ = sum(1 for r in data if r['url'])
print(f'**Hermes agent 公众号文章搜索**')
print()
print(f'搜到 {total} 篇 → 提取 {total} 篇 → {succ} 篇有链接（成功率 {100*succ//max(total,1)}%）')
print()
print('🔥 Top 10：')
print()
for i, r in enumerate(data[:10]):
    if r['url']:
        print(f\"{i+1}. [{r['title']}]({r['url']}) — {r['date']}\")
"
```

回复用户时只发摘要，完整数据存 `/tmp/urls.json`。

---

## Step 5: 完成后的清理

**不关浏览器！** 只清理 mp.weixin.qq.com 标签页，保留微信读书页。

```bash
WINDOWS_IP=$(ip route | grep default | awk '{print $3}')

# 关闭所有 mp.weixin.qq.com 标签页
python3 -c "
import json, subprocess
result = subprocess.run(['curl', '-s', 'http://$WINDOWS_IP:9223/json'], capture_output=True, text=True)
targets = json.loads(result.stdout)
for t in targets:
    if t['type'] == 'page' and 'mp.weixin.qq.com' in t.get('url', ''):
        subprocess.run(['curl', '-s', '-o', '/dev/null', f'http://$WINDOWS_IP:9223/json/close/{t[\"id\"]}'])
        print(f'Closed: {t[\"url\"][:60]}')
print('Done — weread page kept open')
"

# 回到微信读书首页
agent-browser goto "https://weread.qq.com/"
```

---

## 完整陷阱表

| 陷阱 | 解决方案 |
|------|---------|
| `agent-browser --cdp <WS_URL>` 返回 404（WSL） | 用 `agent-browser connect "http://<IP>:9223"` 建立连接 |
| agent-browser click 登录按钮不弹窗 | 用 eval 触发 |
| iframe "微信快捷登录" 遮挡二维码 | eval 中移除 iframe |
| iframe 内按钮点击无效（跨域） | 直接移除 iframe |
| agent-browser eval 输出被双重引号包裹 | `json.loads(json.loads(raw))`（仅 JSON；简单字符串只用一层） |
| 链接获取效率低 | 用 `batch_extract_urls()` 一次 eval 完成全部提取 |
| 滚动永远卡在 15 篇（Python page WS） | 只有 agent-browser eval 能触发 XHR |
| 滚动永远卡在 15 篇（session 丢失） | 保持 weread.qq.com 标签页活跃 |
| 二维码过期 | 全流程单 terminal 调用，关闭→重新触发→提取 |
| QR 流程拆成多个 terminal 调用 | ❌ 大忌 |
| QR 提取后做验证浪费有效期 | ❌ 提取成功后立刻发 MEDIA |
| 二维码 src 是 data: URI 非 HTTP URL | Python base64 解码，补 padding |
| httpOnly cookie 清不掉 | CDP `Storage.clearCookies` |
| `Network.clearBrowserCookies` 返回 -32601 | 用 `Storage.clearCookies` |
| 搜一搜页面卡「加载中...」 | 清 cookie → 重启浏览器 → 重新扫码 |
| 滚动中途停滞（非 15 篇） | 查「暂无更多内容」= 真上限；3 轮不变 = plateau 兜底 |
| 长滚动不要用 background 进程 | 前台 terminal + 长 timeout（600s） |
| 批量提取 URL 部分错位（~40%） | async + `await sleep(50)` + `awaitPromise: true` |
| 部分链接点进去「参数错误」 | ✅ 已修复：从 `/tmp/urls.json` 读完整 URL |
| execute_code 中搜索页 page WS 匹配失败 | 用 `'search.weixin'`（点号，不是斜杠）匹配 URL |
