# 微信读书搜索 - 完整提取代码模板

## 工作流分界

- **Step 1-3（浏览器+登录+搜索+滚动）**：用 `agent-browser --cdp` terminal 命令。必须 agent-browser 执行滚动（Python page WS 的 `window.scrollTo` 不触发 XHR）。
- **Step 4（元数据采集 + URL 批量提取）**：用 `execute_code` 中的 Python + websockets 连搜索页的 **page-level CDP WebSocket**。一次 `Runtime.evaluate` 批量完成全部 URL 提取。

## 快速参考

适用的任务：连接 CDP → 采集元数据 → 筛选 → 获取 URL。在 `execute_code` 中执行。

## 完整模板

```python
import asyncio, json, subprocess, sys, re
from datetime import datetime, timedelta

WINDOWS_IP = "172.19.80.1"
CDP_PORT = 9223

# ── 1. 获取搜索页面 WebSocket URL ──
result = subprocess.run(['curl', '-s', f'http://{WINDOWS_IP}:{CDP_PORT}/json'],
                       capture_output=True, text=True)
targets = json.loads(result.stdout)
ws_url = None
for t in targets:
    if t['type'] == 'page' and 'search.weixin' in t.get('url', ''):
        ws_url = t['webSocketDebuggerUrl']
        break
if not ws_url:
    raise RuntimeError("Search page not found in CDP targets")

import websockets

# ── 2. 辅助函数 ──

async def extract_articles(ws):
    """提取当前 DOM 中所有文章元数据"""
    js = """
    (function() {
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
        return arts;
    })()
    """
    await ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                               'params': {'expression': js, 'returnByValue': True}}))
    msg = await asyncio.wait_for(ws.recv(), timeout=5)
    return json.loads(msg).get('result', {}).get('result', {}).get('value', [])


async def click_get_url(ws, dom_idx):
    """
    已废弃。改用 batch_extract_urls() 一次 eval 批量完成所有提取。
    """
    pass


async def batch_extract_urls(ws, target_indices):
    """
    一次 eval 批量提取所有目标文章的 URL。
    关键：点击 .search_list_item（整个卡片），不是 .article__title-text。
    拦截 window.open（return null 防跳转），每次 click 后 await sleep(50ms) 等 Vue 异步处理。
    N 篇约 N×50ms。
    """
    idx_list = json.dumps(target_indices)
    js = (
        "(async function() {\n"
        "    var sleep = function(ms) { return new Promise(function(r) { setTimeout(r, ms); }); };\n"
        "    var targets = " + idx_list + ";\n"
        "    var allItems = document.querySelectorAll('.search_list_item');\n"
        "    var results = [];\n"
        "    var origOpen = window.open;\n"
        "    for (var i = 0; i < targets.length; i++) {\n"
        "        var idx = targets[i];\n"
        "        var el = allItems[idx];\n"
        "        if (!el) { results.push({idx: idx, url: ''}); continue; }\n"
        "        var captured = '';\n"
        "        window.open = function(u) { captured = u; return null; };\n"
        "        el.scrollIntoView({block: 'center', behavior: 'instant'});\n"
        "        el.click();\n"
        "        await sleep(50);\n"
        "        results.push({idx: idx, url: captured});\n"
        "    }\n"
        "    window.open = origOpen;\n"
        "    return JSON.stringify(results);\n"
        "})()"
    )
    await ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                               'params': {'expression': js, 'returnByValue': True, 'awaitPromise': True}}))
    msg = await asyncio.wait_for(ws.recv(), timeout=60)
    result = json.loads(msg).get('result', {}).get('result', {}).get('value', '[]')
    if isinstance(result, str):
        return json.loads(result)
    return result


def close_mp_weixin_tabs():
    """关闭所有 mp.weixin.qq.com 标签页（保留搜索页面）"""
    result = subprocess.run(['curl', '-s', f'http://{WINDOWS_IP}:{CDP_PORT}/json'],
                           capture_output=True, text=True)
    targets = json.loads(result.stdout)
    closed = 0
    for t in targets:
        if t['type'] == 'page' and 'mp.weixin.qq.com' in t.get('url', ''):
            subprocess.run(['curl', '-s', '-o', '/dev/null',
                f'http://{WINDOWS_IP}:{CDP_PORT}/json/close/{t["id"]}'])
            closed += 1
    return closed


def parse_date(date_str):
    """解析相对时间字符串 → datetime"""
    now = datetime.now()
    if not date_str:
        return None
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


# ── 3. 主流程（提取全部文章）──

async def extract_all(ws):
    """
    提取全部已加载文章（滚动完成后调用）。
    先采集元数据，再批量提取 URL。150 篇 ~0.6s。
    """
    # 3.1 采集元数据
    all_data = await extract_articles(ws)
    total = len(all_data)
    print(f"Articles: {total}")
    
    # 3.2 批量提取全部 URL
    all_indices = list(range(total))
    urls = await batch_extract_urls(ws, all_indices)
    
    # 3.3 组装结果（含日期转换）
    url_map = {u['idx']: u['url'] for u in urls}
    results = []
    for a in all_data:
        raw_date = a.get('date', '')
        parsed = parse_date(raw_date)
        if parsed:
            date_str = parsed.strftime('%Y-%m-%d')
        else:
            date_str = raw_date
        results.append({
            'idx': a['idx'],
            'title': a['title'],
            'source': a['source'],
            'date': date_str,
            'url': url_map.get(a['idx'], '')
        })
    
    success = sum(1 for r in results if r['url'])
    print(f"URLs: {success}/{total} ({100*success//total}%)")
    return results


async def extract_filtered(ws, target_indices, all_articles_data):
    """仅提取指定索引的文章 URL（需提前加载元数据到 all_articles_data）"""
    urls = await batch_extract_urls(ws, target_indices)
    url_map = {u['idx']: u['url'] for u in urls}
    results = []
    for dom_idx in target_indices:
        a = all_articles_data[dom_idx] if dom_idx < len(all_articles_data) else {}
        results.append({
            'idx': dom_idx,
            'title': a.get('title', ''),
            'source': a.get('source', ''),
            'date': a.get('date', ''),
            'url': url_map.get(dom_idx, '')
        })
    return results


# 执行
articles = asyncio.run(main(recent_indices, all_data))
with open('/tmp/urls.json', 'w') as f:
    json.dump(articles, f, ensure_ascii=False, indent=2)
print(f"Done: {sum(1 for a in articles if a['url'])}/{len(articles)} URLs")
```

## 关键注意事项

1. **滚动 vs 提取分离**：滚动（Step 3）用 `agent-browser --cdp` 的 terminal 命令；提取（Step 4）用本模板的 Python + page-level CDP WebSocket。**不要用 Python page WS 做滚动** — `Runtime.evaluate` 执行的 `window.scrollTo` 不会触发搜索页的无限滚动 XHR。只有 agent-browser 的 eval 能触发。实测：agent-browser 3轮滚动 → 60→105→150篇，Python page WS 始终卡在15篇。
2. **批量 eval 提取（async + await sleep）**：一次 `Runtime.evaluate`（`awaitPromise: true`）完成所有 URL 提取。点击 `.search_list_item`（卡片 DIV），不是 `.article__title-text`。拦截 `window.open`（`return null` 防跳转）→ `.click()` 触发 Vue → `await sleep(50)` 等 Vue 异步 handler → 读 `captured`。N 篇约 N×50ms。**不加 await sleep 会导致 ~40% URL 错位**（`captured` 被下一轮覆写）。
3. **无需关闭标签页**：`window.open` 被拦截，不真正打开新标签页。
4. **URL 验证**：提取后用 CDP 浏览器 `goto` 抽查 3-5 条，确认页面加载了文章标题（而非空壳/参数错误）。不要用 curl 验证——curl 可能拿到空壳模板但 HTTP 200。也不要因部分链接「参数错误」反复调整 URL 编码——这是微信服务端行为，与提取无关。
5. **元数据采集可选**：如果已通过 agent-browser 采集了 `/tmp/arts.json`，可跳过 `extract_articles`，直接用 `extract_filtered`。读取文件时注意 `agent-browser eval` 输出被双重引号包裹（`"[{...}]"` 而非 `[{...}]`），需嵌套解析：

```python
with open('/tmp/arts.json', 'r') as f:
    raw = f.read().strip()

# Handle agent-browser eval double-quoting: parse repeatedly until we get a list
all_data = raw
for _ in range(5):
    try:
        all_data = json.loads(all_data)
    except (json.JSONDecodeError, TypeError):
        break
    if not isinstance(all_data, str):
        break

if isinstance(all_data, str):
    raise RuntimeError(f"Failed to parse /tmp/arts.json after 5 rounds")
```

`all_data` 的结构与 `extract_articles()` 返回的一致，可直接喂给 `extract_filtered()` 或 `batch_extract_urls()`。
6. **`Page.enable`**：保留但不再依赖 CDP 事件监听。
7. **🚨 URL 防截断**：`extract_all` 后将 `results` 写入 `/tmp/urls.json`。回复用户时用 terminal 中 Python 脚本从 `/tmp/urls.json` 读取并 print Markdown Top 10，复制到回复。**严禁从 execute_code 控制台 print 输出中复制 URL**（可能截断缺参数）。
