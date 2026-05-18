# wechat-search-weread

[![GitHub](https://img.shields.io/badge/GitHub-KANIKIG%2Fwechat--search--weread-blue?logo=github)](https://github.com/KANIKIG/wechat-search-weread)
[![ClawHub](https://img.shields.io/badge/ClawHub-wechat--search--weread-orange)](https://clawhub.ai/skills/wechat-search-weread)

通过微信读书搜一搜，搜索微信公众号文章。返回**标题、公众号、发布时间、简介**以及 **`mp.weixin.qq.com` 直链**。

> ⚠️ **本项目只负责搜索和获取文章链接，不包含抓取文章正文内容。**

## 和其他方案比

| 方案 | 文章时效 | 有发布日期 | 有直链 | 需要 |
|------|---------|-----------|--------|------|
| **微信读书搜索（本项目）** | ✅ 最新 | ✅ | ✅ | 微信扫码 |
| Exa (mcporter) | ❌ | ❌ | ✅ | API Key |
| 搜狗微信搜索 | ❌ ~2021 | ✅ | ✅ | 无 |

**唯一能同时拿到「最新文章 + 发布日期 + 直链」的方案。**

## 使用方式

通过 Agent 对话触发。在聊天窗口告诉 Agent 你要搜什么即可：

> "搜一下最近关于大模型的公众号文章"
> "微信搜索 OpenAI"

Agent 会自动调用本 Skill 完成搜索。

**如果微信读书还没登录**，Agent 会把登录二维码发到聊天窗口，微信扫码即可。登录后继续搜索，全程自动。

搜索完成后，你会收到：

```
关键词 公众号文章搜索

搜到 258 篇 → 提取 258 篇 → 252 篇有链接（成功率 98%）

🔥 Top 10：

1. [文章标题](http://mp.weixin.qq.com/s/...) — 2小时前
2. [文章标题](http://mp.weixin.qq.com/s/...) — 昨天
...
```

默认展示前 10 篇，完整数据保存在 `/tmp/urls.json`。

## 原理简述

微信读书搜索结果页面本身不暴露文章链接。点击文章卡片时页面通过 `window.open` 打开目标文章。本项目通过浏览器自动化拦截这个操作，批量获取所有文章的真实 `mp.weixin.qq.com` 链接。

## 依赖

- [agent-browser](https://github.com/vercel-labs/agent-browser) — 浏览器自动化控制

## 声明

- 本项目**仅搜索公众号文章并获取链接**，不抓取正文
- 需要微信扫码登录，session 过期后需重新扫码
