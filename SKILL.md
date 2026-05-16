---
name: wechat-search-weread
description: 通过微信读书搜索公众号文章。需要 agent-browser + 微信读书登录态。返回标题/公众号/时间/简介/缩略图/文章链接。
category: social-media
---

# 微信读书公众号文章搜索

通过微信读书（weread.qq.com）的搜一搜功能搜索微信公众号文章，返回完整数据（含 `mp.weixin.qq.com` 文章链接）。

## 触发条件

用户需要搜索微信公众号文章，且 Exa 和搜狗方案不满足需求时使用。

## 前提条件

- [agent-browser](https://github.com/vercel-labs/agent-browser) 已安装
- 微信读书已登录

> 🖥️ **WSL 用户**：需要额外配置让 agent-browser 连接 Windows CDP 浏览器，详见 [references/wsl-cdp-browser.md](references/wsl-cdp-browser.md)。配置完成后，以下所有 `agent-browser` 命令需加上 `--cdp "$WS_URL"` 前缀（`WS_URL` 为 CDP WebSocket 地址）。
>
> 非 WSL 用户直接使用以下命令即可，agent-browser 会自动管理浏览器。

---

## 流程

> ⚠️ **工作流：Step 1-3（浏览器+登录+滚动）用 `agent-browser` 命令。Step 4（提取 URL）用 `execute_code` 中的 Python + websockets 直接连 page-level CDP WebSocket 做批量 eval 提取。** `scripts/search_weread.py` 是备选/调试工具，非主流程。
>
> 🚨 **全流程五步缺一不可**：启动 → 登录 → 搜索+滚动 → **提取URL+格式化输出** → 清理浏览器。**Step 4 是最容易漏的**——滚动完看数字就停是经典错误。Step 4 产出用户真正要的带链接文章列表。
>
> ⚠️ **黄金法则：每一步操作后都等 6-10 秒！页面元素需要时间加载。**
>
> ⚠️ **长滚动（>3 轮）必须用前台 terminal + 长 timeout（600s）**，不要用 background 进程。background 进程 agent-browser daemon 死后无声卡住、输出缓冲为空，无法诊断。
> 
> **例外：QR 登录流程中不要做中间 snapshot 确认**——QR 码有效期极短（~1-2 分钟），从弹窗出现到发码控制在 10 秒内，否则必过期。详见 Step 2.2。

### Step 1: 启动浏览器

**非 WSL**：跳过，agent-browser 自动管理浏览器。

**WSL 用户**：参考 [references/wsl-cdp-browser.md](references/wsl-cdp-browser.md) 启动 Edge CDP 并配置端口转发。

> 验证连接：`agent-browser get cdp-url`（非WSL）或 `curl http://<IP>:9223/json/version`（WSL）

### Step 2: 登录微信读书（统一用扫码！）

**不管弹出什么界面，最终目标都是二维码扫码登录。**

#### 2.0 清除旧登录态（可选，当 cookie 残留时）

微信读书的认证 cookie 是 httpOnly 的，JS 的 `document.cookie = '...=;expires=...'` 和 `localStorage.clear()` 都清不掉。需要用 CDP 的 `Storage.clearCookies`（**page 级别** WebSocket，不是 browser 级别）：

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

> ⚠️ `Network.clearBrowserCookies` 在此 Edge 版本（148）上返回 `-32601 method not found`。只用 `Storage.clearCookies`。
>
> **获取 CDP WebSocket URL 的方法：**
> - 非 WSL：`agent-browser get cdp-url`
> - WSL：`curl -s "http://$WINDOWS_IP:9223/json/version" | python3 -c "import sys,json; print(json.load(sys.stdin)['webSocketDebuggerUrl'])"`

清除后 reload 页面确认"登录"链接出现（而非"我的书架"）。

#### 2.1 导航并点击登录

```bash
agent-browser goto "https://weread.qq.com/"
sleep 8
```

**触发登录弹窗（优先用 eval，`click <ref>` 经常不触发弹窗）：**

```bash
# ✅ 方法 1（推荐）：eval 触发（弹窗加载只需 ~3-5 秒，不要等 10 秒浪费 QR 时间）
agent-browser eval "document.querySelectorAll('a').forEach(a => { if (a.textContent.includes('登录')) a.click(); })"
sleep 6

# ⚠️ 方法 2（备选）：agent-browser click — 经常无效
# agent-browser snapshot | grep -i 登录
# agent-browser click <登录的ref>
# sleep 6
```

#### 2.2 登录决策（默认「刷新后提取」，保证新鲜 QR）

> ⚠️ **首次 eval 触发的 QR 经常是旧缓存的（已失效），必须关闭弹窗后重新触发一次。**
> 
> - QR 码有效期很短（~1-2 分钟），不要做中间 snapshot 确认
> - 首次 eval → 弹窗可能用旧 DOM 缓存渲染已过期 QR
> - 必须：关闭弹窗 → 重新触发 → 再提取，才能拿到新鲜 QR

**默认流程（关闭 → 重新触发 → 一气呵成提取，全部放在一个 terminal() 调用里！）：**

> ⚠️ **必须用一个 terminal() 调用跑完 Step A-E！** 不要拆分——每次单独的 terminal() 调用都有进程启动/agent-browser 握手延迟，加起来浪费 10-20 秒，QR 早过期了。一旦开始 QR 流程就不要停下来做 snapshot、验证或问用户问题，直到发码完成。

```bash
# Step A: eval 触发第一次登录（仅用于唤起弹窗，5s 足够）
agent-browser eval "document.querySelectorAll('a').forEach(a => { if (a.textContent.includes('登录')) a.click(); })"
sleep 5

# Step B: 关闭弹窗（丢弃旧 QR）
agent-browser eval "var m=document.querySelector('.mask,.dialog_mask,.wr_overlay');if(m)m.click();'closed'"
sleep 2

# Step C: 重新触发登录（拿到新鲜 QR，6s 即可——弹窗加载只需 3-5s）
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

# Step E: 解析并下载 QR → 立即发码给用户（不做验证！验证浪费 QR 有效期）
python3 -c "
import json, base64, os
with open('/tmp/qr_url.txt') as f:
    raw = f.read().strip()
src = json.loads(raw)
if not src:
    print('ERROR: no QR image found')
    exit(1)
if src.startswith('data:image'):
    # data: URI base64 may omit padding chars — split on comma, pad, decode
    b64 = src.split(',', 1)[1]
    b64 += '=' * (4 - len(b64) % 4) if len(b64) % 4 else ''
    with open('/tmp/weread_qr.png', 'wb') as f:
        f.write(base64.b64decode(b64))
else:
    import subprocess; subprocess.run(['curl', '-s', '-o', '/tmp/weread_qr.png', src])
print(f'QR OK: {os.path.getsize(\"/tmp/weread_qr.png\")} bytes')
"
# 整个 block 结束后立刻在回复里发 MEDIA:/tmp/weread_qr.png，不要做任何中间检查
```

**如果 QR 仍失效（极少情况）：** 重复 Step B-D（关闭→重新触发→提取）。如果登录弹窗完全消失，重新 goto + 触发：
```bash
agent-browser goto "https://weread.qq.com/"
sleep 6
agent-browser eval "document.querySelectorAll('a').forEach(a => { if (a.textContent.includes('登录')) a.click(); })"
sleep 6
# 再次一键提取
```

**发送二维码图片给用户扫码：**
在回复中包含 `MEDIA:/tmp/weread_qr.png`，等待用户确认已扫码。

**验证登录：**
```bash
agent-browser goto "https://weread.qq.com/"
sleep 6
agent-browser snapshot | grep -i "我的书架\|继续阅读"
```

### Step 3: 搜索 + 大批量滚动加载

> ⚠️⚠️⚠️ **铁律：微信读书（weread.qq.com）标签页绝对不能关！绝对不能离开！绝对不能 navigate away！** 
> 
> 搜索页的无限滚动 XHR 请求依赖 weread.qq.com 标签页的 session cookie。一旦关闭或导航走 weread 标签页，搜索结果将永远卡在初始 15 篇，无论怎么滚动都不会加载更多。整个流程中 weread 标签页必须保持打开且已登录。
>
> 🔴 **滚动必须用 agent-browser 的 eval 执行**，不能通过 Python page WS 直连。`window.scrollTo` 在 CDP `Runtime.evaluate` 上不会触发 XHR 请求，只有 agent-browser 的 eval 能触发。Step 4 提取 URL 才用 Python page WS。

#### 3.1 导航到搜索页 + 保持 weread session

> 🔴 **核心流程**：agent-browser goto 搜索页后可能影响 weread session。需要保持 weread.qq.com 标签页活跃。

```bash
# A. agent-browser goto 搜索页
agent-browser goto \
  "https://search.weixin.qq.com/cgi-bin/newsearchweb/userclientjump?path=page/search/weread&query=URL编码关键词&platform=pc"
sleep 8
agent-browser eval "document.querySelectorAll('.search_list_item').length"

# B. 保持 weread 标签页活跃 — 非WSL用户可能需要用 CDP Target.createTarget
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

# C. agent-browser 重新 goto 搜索页（确保 session 关联正常）
agent-browser goto \
  "https://search.weixin.qq.com/cgi-bin/newsearchweb/userclientjump?path=page/search/weread&query=URL编码关键词&platform=pc"
sleep 8
agent-browser eval "document.querySelectorAll('.search_list_item').length"
# → 初始 15 篇
```

> ⚠️ 步骤 B-C 是关键：如果没有保持 weread session，滚动可能永远卡在 15 篇。

#### 3.2 滚动加载（默认滚到「暂无更多内容」，500 条封顶）

> 🎯 **默认策略**：一直滚到页面出现「暂无更多内容」为止。如果滚动超过 500 条还未出现，提前停止（避免无限空滚）。

```bash
# 每轮 = 3 次 scrollTo + 2s 间隔 + 3s 渲染等待。每轮新增 ~45 篇。
# 默认滚到「暂无更多内容」，超过 500 条封顶。
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

# ⚠️ 滚动完成后 → 立刻进 Step 4 提取 URL + 格式化输出，不要停在这里！
```

> 典型增长曲线：R1→60, R2→105, R3→150, R4→195, R5→240, R6→258（然后持平）。
> 每轮新增 ~45 篇，直到搜索索引上限。达到上限后连续多轮不变。
>
> ⚠️ **如果两轮滚动后数量不变（如始终 15 篇）：**
> 1. **最常见原因：weread session 丢失** — 确保 weread.qq.com 标签页仍然活跃且保持登录态
> 2. ⚠️ **不要用 Python page WS 做滚动** — `Runtime.evaluate` 执行的 `window.scrollTo` 不会触发 XHR，只有 agent-browser 的 eval 能触发。

### 🔴 Step 4: 提取文章数据 + URL（eval 批量方案）——**必须执行，不可跳过！**

> 🚨 **Step 3 滚动结束后绝对不能停！不能只报滚动数字就完事！必须执行 Step 4 提取 URL + 按 4.4 格式输出 Top 10！**
>
> 如果用户只要你搜文章数量或测试滚动，Step 4 仍然必须做——用户要的最终产出物是带链接的文章列表，不是滚动日志。
>
> ⚠️ **一次 eval 批量提取所有 URL**。点击 `.search_list_item`（整个卡片）→ 拦截 `window.open` → 读 URL。N 篇约 N×50ms（async+await 防竞态）。**不要用 CDP Input.dispatchMouseEvent。**

#### 4.1 批量采集文章元数据

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

⚠️ **关键**：`agent-browser eval` 返回的字符串被**双重引号包裹**（`"[...]"`），解析需 `json.loads(json.loads(raw))`。

#### 4.2 筛选目标文章

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

#### 4.3 获取文章 URL（execute_code 中执行，一次 eval 批量完成）

> 用 `execute_code` 执行 Python（sandbox 内置 `websockets`），通过搜索页的 **page-level CDP WebSocket** 直连。一次 `Runtime.evaluate` 完成全部 URL 提取。
>
> **获取 CDP WebSocket URL：**
> - 非 WSL：`agent-browser get cdp-url` 得到浏览器级 WS → 访问 `/json` 获取 page targets
> - WSL：`curl -s "http://$WINDOWS_IP:9223/json"` 获取 page targets

完整代码见 `references/extraction-pattern.md`。核心 JS（async + await sleep 防竞态）：

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
- 必须用 async function + `await sleep(50)` + `awaitPromise: true`，否则 Vue 异步 handler 导致 ~40% URL 错位

#### 4.4 输出格式

**操作：** execute_code 提取完成后，URL 已写入 `/tmp/urls.json`。在 terminal 中用 Python 一行脚本从 json 读数据并 print Markdown Top 10，输出到终端后直接复制到回复中。**严禁从 execute_code 控制台输出中复制 URL。**

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

**回复用户时只发摘要，不要全文罗列所有文章。完整数据存 `/tmp/urls.json`。**
- ⚠️ 输出后追加一行提示：`> 💡 如在微信内点链接提示「参数错误」，这是微信的反爬限制（与URL格式无关）。需要的话我可以帮你抓取全文发过来~`
```

### Step 5: 完成后的清理

**关闭浏览器！**

```bash
# 非WSL
agent-browser close

# WSL
/mnt/c/Windows/System32/taskkill.exe /F /IM msedge.exe
```

---

## 原理

### 搜索 API

页面通过 `https://weread.qq.com/web/wx_search_broker_proxy` (XHR POST) 加载搜索结果。API 需要 session cookie（httpOnly），外部无法直接调用。

### URL 获取（eval 拦截方案）

DOM 中无 href。点击 `.search_list_item`（卡片 DIV，有 `__vue__` 属性）→ Vue 事件委托 → `window.open(mp.weixin.qq.com/s?...)`。通过 eval 注入拦截 `window.open`，原生 `.click()` 触发 Vue 事件，读 intercepted URL。15篇测试 100% 成功，~0.5s 完成。

**不需要 CDP Input.dispatchMouseEvent**（已废弃）。原生 `.click()` 触发完整事件链，Vue 能正确捕获。`dispatchEvent(new MouseEvent(...))` 也有效（isTrusted 不影响）。

### 滚动加载

无限滚动。每次滚动触发 XHR 加载 30-45 篇新文章，追加到 DOM 末尾。

### 去重

每篇文章有唯一 `data-id`（格式 `{msg_id}&{idx}`）。

---

## 常见陷阱

| 陷阱 | 解决方案 |
|------|---------|
| agent-browser click 登录按钮不弹窗 | 用 `eval` 触发：`document.querySelectorAll('a').forEach(a => { if (a.textContent.includes('登录')) a.click(); })` |
| iframe "微信快捷登录" 遮挡二维码 | 直接移除 iframe：`eval` 中 `document.querySelectorAll('iframe').forEach(f => f.remove())` |
| iframe 内按钮点击无效（跨域） | 不要反复点击 iframe 按钮，直接移除 iframe |
| agent-browser eval 输出被双重引号包裹 | `json.loads(json.loads(raw))` — ⚠️ 仅适用 JSON 对象/数组。简单字符串只有一层引号包裹，用 `json.loads(raw)` 即可，双重解包会失败 |
| JS 模拟点击无法触发 Vue 事件 | ~~用 CDP Input.dispatchMouseEvent~~ 已废弃。现在用 native `.click()` on `.search_list_item`（整个卡片 DIV）+ eval 拦截 `window.open`。100% 成功。不要点 `.article__title-text`（标题文字），要点卡片元素 |
| 链接获取效率低 | 用 `batch_extract_urls()` 一次 eval 完成全部提取。60 篇 ~0.5s。详见 `references/extraction-pattern.md` |
| 滚动永远卡在 15 篇（Python page WS） | ❌ Python page WS 的 `Runtime.evaluate` 执行 `window.scrollTo` 不会触发无限滚动 XHR。**只有 agent-browser 的 eval 能触发**。Step 3 全部用 agent-browser，Step 4 提取才用 Python page WS |
| 滚动永远卡在 15 篇（weread session 丢失） | 最常见原因：需在 goto 搜索页后保持 weread.qq.com 标签页活跃。详见 Step 3.1 |
| 登录弹窗加载慢，没看到二维码就提取了 | ~~先 snapshot 确认~~ ❌ snapshot 会浪费 QR 有效期。直接一键提取（移除 iframe + 提取 src + 下载），中间不做 snapshot |
| 二维码过期 | 默认已处理：主流程总是「关闭→重新触发→提取」。⚠️ **整个 QR 流程必须用一个 terminal() 调用跑完**——拆分成多个 terminal() 会累积进程启动延迟。如果仍过期，重新 goto → 重复关闭→触发→提取 |
| QR 流程拆成多个 terminal() 调用导致过期 | ❌ 大忌！必须把 goto + Step A-E 全部放进一个 terminal()，中间不做 snapshot、不验证、不问用户 |
| QR 提取后做验证浪费有效期 | ❌ 不要验证。提取成功后立刻发 MEDIA 给用户。src 为空是唯一的失败信号 |
| 二维码 src 是 data: URI 而非 HTTP URL | curl 无法下载 data: URI；用 Python base64 解码（见 Step 2.2 步骤 E）。⚠️ data URI 的 base64 可能缺少 padding，解码前补 `=` 号 |
| httpOnly cookie 清不掉（document.cookie 无效） | 用 CDP `Storage.clearCookies` 通过 page 级别 WS（见 Step 2.0） |
| `Network.clearBrowserCookies` 返回 -32601 | Edge 版本不支持该方法，用 `Storage.clearCookies` 代替 |
| 搜一搜页面卡在「加载中...」永不消失 | 登录态 cookie/session 过期。**不能靠点搜索按钮解决**。清 cookie → 重启浏览器 → 重新扫码登录 |
| 微信读书标签页被关闭导致滚动失效 | ❌❌❌ 最致命的错误！weread.qq.com 标签页绝对不能关。搜索页的无限滚动 XHR 依赖该 session。一旦关闭，滚动永远卡初始 15 篇 |
| 滚动中途停滞（非 15 篇）— 是真上限还是 session 断了？ | **两步确诊**：① 先查「暂无更多内容」返回 `true` = 确定性终止。② 连续 3 轮不变 = plateau 兜底。如果一开始卡 15 才是 session 丢失 |
| 长滚动（>3 轮）不要用 background 进程 | ❌ `background=true` 的 terminal 可能无声卡住。**超过 3 轮滚动必须用前台 terminal + 长 timeout（600s）** |
| 批量提取 URL 部分错位（~40%） | Vue 异步调用 `window.open`。**修复：async function + `await sleep(50)` + `awaitPromise: true`** |
| 部分链接点进去「参数错误」 | ⚠️ 不是提取 bug！某些 mp.weixin.qq.com 文章服务端返回「参数错误」是微信的反爬/权限控制，与 URL 格式无关。**用户反馈时：① 立即用 CDP 浏览器抽查 2-3 条验证链接正常；② 主动 offer 帮用户 CDP 抓取全文内容发过来；③ 不要在链接格式、编码上浪费时间调试** |

---

## References

- `references/extraction-pattern.md` — 完整可运行的 Python 提取代码模板（eval 批量提取 URL + 元数据采集 + 日期解析），`execute_code` 中直接执行
- `references/cdp-patterns.md` — CDP 交互模式参考：browser vs page 级别、关键命令、常见错误与调试技巧
- `references/wsl-cdp-browser.md` — WSL 用户配置 CDP 浏览器连接指南
- `scripts/search_weread.py` — **备选/调试用 Python 脚本**，非主流程。主流程用 agent-browser 命令即可。仅在 agent-browser 完全不可用时考虑此脚本。
