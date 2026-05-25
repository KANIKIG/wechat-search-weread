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

> 🔴 **全部详细命令、代码块、陷阱表见 [references/detailed-workflow.md](references/detailed-workflow.md)**。

## 原理简述

- **搜索 API**: 页面 XHR → `weread.qq.com/web/wx_search_broker_proxy`（需 session cookie）
- **URL 获取**: DOM 无 href，点击 `.search_list_item` → Vue → `window.open(mp.weixin.qq.com/...)` → eval 拦截
- **滚动加载**: 每次 scrollTo 触发 XHR 加载 ~45 篇新文章
- **去重**: 每篇文章有唯一 `data-id`

## 结果投递

搜索完成后，**直接以最终回复输出结果**，系统会自动投递到当前对话。

输出格式（Step 4.4）：搜到 X 篇 → 提取 Y 篇 → Z 篇有链接（成功率 N%）+ Top 10 列表，完整数据存 `/tmp/urls.json`。

## References

- `references/detailed-workflow.md` — **完整操作手册**：Step 1-5 全部命令、QR 流程、滚动策略、URL 提取代码
- `references/extraction-pattern.md` — Python 提取代码模板（execute_code 中直接执行）
- `references/cdp-patterns.md` — CDP 交互模式参考
- `references/wsl-cdp-browser.md` — WSL 配置指南
- `references/api-limitations.md` — 微信读书 API 限制说明
- `references/llm-filter-pattern.md` — LLM 语义筛选模式：搜索噪音过滤（替代关键词黑名单）
- `scripts/search_weread.py` — 备选/调试脚本（非主流程）
