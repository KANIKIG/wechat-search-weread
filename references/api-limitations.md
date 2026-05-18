# 微信读书官方 Agent API 限制

## 背景

微信读书提供了官方 Agent API（`POST https://i.weread.qq.com/api/agent/gateway`，需 API Key），声称通过 `/store/search` 的 `scope` 参数支持搜索公众号（scope=2）和文章（scope=4）。

## 实测结论

| scope | 名称 | 状态 | 说明 |
|-------|------|------|------|
| 0 | 全部 | ✅ | 搜书（电子书/有声书/书单等） |
| 10 | 电子书 | ✅ | 正常 |
| 12 | 全文 | ✅ | 搜书内正文，返回 `currentCount=0` |
| 2 | 公众号 | ❌ `-2041` | 不可用 |
| 4 | 文章 | ❌ `-2041` | 不可用 |

**公众号文章搜索（scope=2/4）在后端未对 Agent API Key 开放。** 浏览器方案（weread.qq.com 搜一搜 + CDP 提取）是当前唯一的公众号文章搜索途径。

## 测试时间

2026-05-17，API Key `wrk-FGVctlbTTPaWm7gmFFAi7gAA`，skill_version 1.0.3。
