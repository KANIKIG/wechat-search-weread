# wechat-search-weread

通过微信读书（weread.qq.com）搜一搜功能搜索微信公众号文章，可获取文章标题、公众号、发布时间、简介和 `mp.weixin.qq.com` 文章链接。

## 原理

微信读书搜索页面通过 XHR 加载结果，DOM 中无直接链接。通过 CDP 浏览器控制搜索页，滚动加载全部结果后用 JS 拦截 `window.open` 批量提取链接。

## 依赖

- Windows Edge CDP 浏览器（debug port 9222）
- 微信读书登录态
- agent-browser（CDP 控制）
- Python 3 + websockets

## 使用方法

详见 [SKILL.md](./SKILL.md)。
