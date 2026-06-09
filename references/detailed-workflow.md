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

**WSL 用户**：参考 [wsl-cdp-browser.md](wsl-cdp-browser.md) 启动浏览器 CDP 并配置端口转发。

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

> `Network.clearBrowserCookies` 在 CDP 可能返回 `-32601`，只用 `Storage.clearCookies`。

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
# A. 先保留登录会话（在导航走之前创建 weread 备份标签页）
#    获取 browser WS URL（非WSL: agent-browser get cdp-url，WSL: curl http://IP:9223/json/version）
python3 -c "
import asyncio, json, subprocess, websockets
WINDOWS_IP = subprocess.run(['ip', 'route'], capture_output=True, text=True).stdout.split('default via ')[1].split()[0] if 'default via ' in subprocess.run(['ip', 'route'], capture_output=True, text=True).stdout else '172.19.80.1'
result = subprocess.run(['curl', '-s', f'http://{WINDOWS_IP}:9223/json/version'], capture_output=True, text=True)
bw = json.loads(result.stdout)['webSocketDebuggerUrl']

async def create():
    async with websockets.connect(bw, max_size=2**24) as ws:
        await ws.send(json.dumps({'id':1,'method':'Target.createTarget','params':{'url':'https://weread.qq.com/'}}))
        resp = await asyncio.wait_for(ws.recv(), timeout=10)
        print(resp)
asyncio.run(create())
"
sleep 5
```

> 💡 **简易替代**：当 CDP websockets 路径被阻断（cron 禁用 execute_code、安全扫描器拦截 heredoc）时，可用 `agent-browser open "https://weread.qq.com/"` 替代上面的 Python 代码创建备份标签页。效果相同，更简单。
# B. 导航到搜索页（原标签页变为搜索页，备份的 weread 标签页保持登录态）
agent-browser goto \
  "https://search.weixin.qq.com/cgi-bin/newsearchweb/userclientjump?path=page/search/weread&query=URL编码关键词&platform=pc"
sleep 8
agent-browser eval "document.querySelectorAll('.search_list_item').length"
# → 初始 15 篇
```

### 3.2 滚动加载（默认滚到「暂无更多内容」，500 条封顶）

> ⚠️ **CDP 滚动注意事项**：某些 CDP 实现中 `window.scrollTo()` / `scroll down` / `PageDown` 会改变 `scrollY` 但不会触发 `scroll` 事件。搜索页的无限滚动依赖 scroll 事件触发 XHR。**统一做法：每次滚动后手动 `window.dispatchEvent(new Event('scroll'))` 以确保触发加载**。

```bash
# 每轮 = 3 次 [scrollTo + dispatchEvent] + 2s 间隔 + 3s 渲染等待。每轮新增 ~45 篇。
PREV=""; PREV2=""
for r in $(seq 1 20); do
  for j in 1 2 3; do
    agent-browser eval "window.scrollTo(0, document.body.scrollHeight); window.dispatchEvent(new Event('scroll'));" > /dev/null 2>&1
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

如果两轮后数量不变（始终 15 篇）：① weread session 丢失 ② 用了 Python page WS 做滚动 ③ scroll 事件未触发（未加 `dispatchEvent`，见 [edge-cdp-scroll-issue.md](edge-cdp-scroll-issue.md)）。

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
    """解析相对/绝对时间字符串 → datetime。支持：X年前/个月前/周前/天前/小时前/分钟前、YYYY-MM-DD、YYYY/M/D、M月D日、M/D、M-D"""
    now = datetime.now()
    if not date_str:
        return None
    if '年前' in date_str:
        m = re.search(r'(\d+)', date_str)
        return now - timedelta(days=int(m.group(1)) * 365) if m else None
    if '个月前' in date_str:
        m = re.search(r'(\d+)', date_str)
        return now - timedelta(days=int(m.group(1)) * 30) if m else None
    if '周前' in date_str:
        m = re.search(r'(\d+)', date_str)
        return now - timedelta(weeks=int(m.group(1))) if m else None
    if '天前' in date_str:
        m = re.search(r'(\d+)', date_str)
        return now - timedelta(days=int(m.group(1))) if m else None
    if '小时前' in date_str:
        m = re.search(r'(\d+)', date_str)
        return now - timedelta(hours=int(m.group(1))) if m else None
    if '分钟前' in date_str:
        m = re.search(r'(\d+)', date_str)
        return now - timedelta(minutes=int(m.group(1))) if m else None
    if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
        return datetime.strptime(date_str[:10], '%Y-%m-%d')
    if re.match(r'\d{4}/\d{1,2}/\d{1,2}', date_str):
        parts = date_str.split('/')
        return datetime(int(parts[0]), int(parts[1]), int(parts[2]))
    if re.match(r'\d{1,2}/\d{1,2}', date_str):
        parts = date_str.split('/')
        month, day = int(parts[0]), int(parts[1])
        dt = datetime(now.year, month, day)
        return dt if dt <= now else datetime(now.year - 1, month, day)
    if re.match(r'\d{1,2}月\d{1,2}日', date_str):
        m = re.match(r'(\d{1,2})月(\d{1,2})日', date_str)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            dt = datetime(now.year, month, day)
            return dt if dt <= now else datetime(now.year - 1, month, day)
    if re.match(r'\d{1,2}-\d{1,2}', date_str):
        parts = date_str.split('-')
        month, day = int(parts[0]), int(parts[1])
        dt = datetime(now.year, month, day)
        return dt if dt <= now else datetime(now.year - 1, month, day)
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
print(f'**公众号文章搜索结果**')
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

**不关浏览器！** 回到微信读书登录页，关闭搜索页等所有多余标签页，只保留一个 weread 页面。

```bash
WINDOWS_IP=$(ip route | grep default | awk '{print $3}')

# 先回到微信读书首页（agent-browser 标签页变为 weread）
agent-browser goto "https://weread.qq.com/"
sleep 5

# 关闭其他所有标签页（搜索页 + mp.weixin.qq.com + 备份 weread），只保留当前 weread
python3 -c "
import json, subprocess
result = subprocess.run(['curl', '-s', 'http://$WINDOWS_IP:9223/json'], capture_output=True, text=True)
targets = json.loads(result.stdout)
# 第一轮：关掉所有非 weread 页面
for t in targets:
    if t['type'] == 'page' and 'weread.qq.com' not in t.get('url', ''):
        subprocess.run(['curl', '-s', '-o', '/dev/null', f'http://$WINDOWS_IP:9223/json/close/{t[\"id\"]}'])
        print(f'Closed: {t[\"url\"][:80]}')
# 第二轮：如果还有多个 weread 页面，把多余的也关了
result = subprocess.run(['curl', '-s', 'http://$WINDOWS_IP:9223/json'], capture_output=True, text=True)
targets = json.loads(result.stdout)
weread_tabs = [t for t in targets if t['type'] == 'page' and 'weread.qq.com' in t.get('url', '')]
if len(weread_tabs) > 1:
    for t in weread_tabs[1:]:  # 保留第一个，关掉其余的
        subprocess.run(['curl', '-s', '-o', '/dev/null', f'http://$WINDOWS_IP:9223/json/close/{t[\"id\"]}'])
        print(f'Closed duplicate weread: {t[\"id\"]}')
print('Done — only weread login page remains')
"
```

---

## 完整陷阱表

| 陷阱 | 解决方案 |
|------|---------|
| 滚动后 scroll 事件不触发（scrollY变但事件0） | 每次 scrollTo 后手动 `dispatchEvent(new Event('scroll'))` |
| `agent-browser --cdp <WS_URL>` 返回 404（WSL） | 用 `agent-browser connect "http://<IP>:9223"` 建立连接 |
| agent-browser click 登录按钮不弹窗 | 用 eval 触发 |
| iframe "微信快捷登录" 遮挡二维码 | eval 中移除 iframe |
| iframe 内按钮点击无效（跨域） | 直接移除 iframe |
| agent-browser eval 输出被双重引号包裹 | `json.loads(json.loads(raw))`（仅 JSON；简单字符串只用一层） |
| 链接获取效率低 | 用 `batch_extract_urls()` 一次 eval 完成全部提取 |
| 滚动永远卡在 15 篇（scroll 事件不触发） | scrollTo/pageDown/scrollIntoView 改变 scrollY 但不一定触发 scroll 事件。**解决：每次 scrollTo 后手动 `dispatchEvent(new Event('scroll'))`**（见 3.2），无需换浏览器。详见 [edge-cdp-scroll-issue.md](edge-cdp-scroll-issue.md) |
| 滚动永远卡在 15 篇（Python page WS） | 只有 agent-browser eval 能触发 XHR |
| 滚动永远卡在 15 篇（session 丢失） | 保持 weread.qq.com 标签页活跃 |
| 页面显示「加载中」但实际未加载 | 搜索页 body 中「加载中」字符串是**静态模板文本**，不是实时加载指示器。验证滚动是否工作的唯一标准是 `search_list_item` 数量变化。 |
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
| execute_code websockets `recv()` 120s 超时（>50 篇） | 用 agent-browser eval 分批提取（每批 50），已验证 246 篇 100% 成功。不要用 execute_code + websockets 做大批量 URL 提取。 |
| parse_date 不识别「X个月前」「X年前」「X月X日」「2025/3/24」等格式 | 使用 extraction-pattern.md 中的完整 parse_date（已覆盖所有已知格式） |
