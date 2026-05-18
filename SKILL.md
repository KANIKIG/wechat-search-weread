---
name: wechat-search-weread
description: 微信公众号文章搜索skill。通过微信读书搜一搜获取最新文章，返回标题/公众号/时间/简介/直链。
category: social-media
---

# 微信读书公众号文章搜索

> 📦 [GitHub](https://github.com/KANIKIG/wechat-search-weread) · [ClawHub](https://clawhub.ai/skills/wechat-search-weread)

通过微信读书搜一搜搜索微信公众号文章，返回完整数据（含 `mp.weixin.qq.com` 文章链接）。

## 触发条件

用户需要搜索微信公众号文章，且 Exa 和搜狗方案不满足需求时使用。

> ⚠️ 微信读书官方 API (`/store/search` scope=2/4) 不支持公众号文章搜索（返回 `-2041`），详见 [api-limitations.md](references/api-limitations.md)。本浏览器方案是当前唯一可行途径。

## 前提

- [agent-browser](https://github.com/vercel-labs/agent-browser) 已安装
- 微信读书已登录（首次需扫码）
- WSL 用户需 CDP 端口转发（见 [wsl-cdp-browser.md](references/wsl-cdp-browser.md)），用 `agent-browser connect "http://<IP>:9223"` 建连后无需 `--cdp` flag

## 流程概要（5 步，缺一不可）

| 步骤 | 要点 |
|------|------|
| **1. 启动浏览器** | 非WSL自动；WSL 参考 [wsl-cdp-browser.md](references/wsl-cdp-browser.md) |
| **2. 登录** | QR 扫码。首次 eval 触发的 QR 大概率过期 → 必须关闭弹窗→重新触发→提取（单 terminal 调用一气呵成）。**登录成功后删除 `/tmp/weread_qr.png`** |
| **3. 搜索+滚动** | 先备份 weread 标签页（保持登录态）→ goto 搜索页 → eval 滚动到「暂无更多内容」（封顶500条） |
| **4. 提取URL** | execute_code 中 Python + websockets 连 page CDP → 批量点击 → 拦截 window.open → 写入 `/tmp/urls.json` |
| **5. 清理** | 回到微信读书首页 → 关闭搜索页、mp 链接等所有多余标签页，只保留一个 weread 页面 |

> 🔴 **全部详细命令见 [references/detailed-workflow.md](references/detailed-workflow.md)**（含每个 step 的完整 bash 代码）。

### Step 2 QR 清理

```bash
# 登录验证通过后立即删 QR
rm -f /tmp/weread_qr.png /tmp/qr_url.txt
```

### Step 4 输出格式

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

> ⚠️ 从 `/tmp/urls.json` 读取（不是控制台输出），避免 URL 截断。

## 核心陷阱（TOP 5）

| # | 陷阱 | 解决 |
|---|------|------|
| 1 | **weread 标签页被关** → 滚动卡 15 篇 | 整个流程中绝对不能关 weread.qq.com 标签页 |
| 2 | **滚动用 Python page WS** → 不触发 XHR | 只许 `agent-browser eval` 做滚动，Python WS 仅用于 Step 4 URL 提取 |
| 3 | **长滚动用 background** → 无声卡死 | 3轮+ 滚动必须前台 terminal + 600s timeout |
| 4 | **URL 从控制台复制** → 截断（缺失 chksm/#rd） | Step 4.4 强制从 `/tmp/urls.json` 读完整 URL |
| 5 | **QR 流程拆多 terminal** → 过期 | 全流程 Step A-E 必须在同一个 terminal() 调用 |

> 完整陷阱表见 [references/detailed-workflow.md](references/detailed-workflow.md)。

## 原理简述

- **搜索 API**: 页面 XHR → `weread.qq.com/web/wx_search_broker_proxy`（需 session cookie）
- **URL 获取**: DOM 无 href，点击 `.search_list_item` → Vue → `window.open(mp.weixin.qq.com/...)` → eval 拦截
- **滚动加载**: 每次 scrollTo 触发 XHR 加载 ~45 篇新文章
- **去重**: 每篇文章有唯一 `data-id`

## References

- `references/detailed-workflow.md` — **完整操作手册**：Step 1-5 全部命令、QR 流程、滚动策略、URL 提取代码
- `references/extraction-pattern.md` — Python 提取代码模板（execute_code 中直接执行）
- `references/cdp-patterns.md` — CDP 交互模式参考
- `references/wsl-cdp-browser.md` — WSL 配置指南
- `references/api-limitations.md` — 微信读书 API 限制说明
- `references/cron-dedup-pattern.md` — 定时搜索去重持久化模式
- `scripts/search_weread.py` — 备选/调试脚本（非主流程）
