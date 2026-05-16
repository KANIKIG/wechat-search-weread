# wechat-search-weread

通过微信读书（weread.qq.com）搜一搜功能搜索微信公众号文章，返回 **标题、公众号、发布时间、简介** 以及 **`mp.weixin.qq.com` 文章直链**。

> ⚠️ **本项目只负责搜索和获取文章链接，不包含抓取文章正文内容的功能。** 拿到链接后如需正文，请另用 web 抓取工具处理。

## 为什么用这个？

微信公众号文章搜索一直是老大难问题：

| 方案 | 时效性 | 发布日� | 文章链接 | 门槛 |
|------|--------|---------|---------|------|
| **微信读书搜索（本项目）** | ✅ 最新 | ✅ 相对时间 | ✅ mp.weixin.qq.com | 需扫码登录 |
| Exa（mcporter） | ✅ 最新 | ❌ 无 | ✅ | 需 API Key |
| 搜狗微信搜索 | ❌ ~2021 | ✅ 精确 | ✅ | 无 |

**本项目是唯一能同时拿到「最新文章 + 发布日期 + 直链」的方案。**

## 流程概览

整个搜索流程分为五步：

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ 1.启动    │ ──▶ │ 2.扫码登录 │ ──▶ │ 3.搜索+滚动│ ──▶ │ 4.提取链接 │ ──▶ │ 5.清理    │
│ CDP浏览器 │     │ 微信读书  │     │ 加载全部  │     │ 批量获取  │     │ 关闭浏览器│
└──────────┘     └──────────┘     └──────────┘     └──────────┘     └──────────┘
```

### Step 1：启动 CDP 浏览器

启动 Windows Edge 并开启远程调试端口（9222），WSL 通过 `netsh portproxy` 映射到 9223 端口访问。

### Step 2：扫码登录微信读书

这是最关键的一步。微信读书的搜索 API 需要登录态（httpOnly session cookie），外部无法直接调用，必须通过浏览器扫码登录。

**为什么必须扫码：**
- 微信读书不支持账密登录，只能微信扫码
- 二维码有效期极短（~1-2 分钟），所以提取和发送必须一气呵成
- 首次触发的弹窗常渲染旧缓存 QR（已失效），必须关闭后重新触发拿新鲜码

**扫码流程：**
1. 导航到 `weread.qq.com` → 点击「登录」触发弹窗
2. 关闭弹窗（丢弃旧 QR）→ 重新触发登录（拿到新鲜 QR）
3. 移除页面干扰元素（iframe 遮罩）→ 提取 QR 图片
4. 将 QR 发给用户扫码 → 验证登录成功

整个过程必须在一个连续操作中完成，不能停顿，否则 QR 会过期。

### Step 3：搜索 + 滚动加载

导航到微信读书搜一搜页面，通过无限滚动触发 XHR 加载，逐批获取搜索结果，直到「暂无更多内容」或达到上限。

**关键限制：** 搜索页的无限滚动 XHR 依赖微信读书标签页的 session cookie。如果关闭或离开微信读书标签页，滚动将永远卡在初始 15 篇。

### Step 4：批量提取文章链接

DOM 中不包含直接的文章链接。点击文章卡片时，Vue 事件处理会调用 `window.open(mp.weixin.qq.com/s/...)` 打开文章。通过拦截 `window.open` + 逐一点击卡片，批量获取所有文章的 mp.weixin.qq.com 链接。

**这是整个流程的核心产出步骤**——没有这一步，前面的搜索和滚动只是无链接的元数据。

### Step 5：清理

关闭 CDP 浏览器，释放系统资源。

## 技术原理

### 搜索 API

页面通过 `https://weread.qq.com/web/wx_search_broker_proxy`（XHR POST）加载搜索结果。该 API 需要 httpOnly session cookie，无法从外部直接调用，必须在浏览器中保持登录态。

### URL 获取

微信读书搜索结果页的 DOM 中不包含 `mp.weixin.qq.com` 链接。点击 `.search_list_item`（文章卡片 DIV，带 `__vue__` 属性）→ Vue 事件委托 → 调用 `window.open(url)` 打开文章页面。

通过 CDP 注入 JS 拦截 `window.open`，再用原生 `.click()` 触发 Vue 事件链，读取被拦截的 URL。采用 `async function` + `await sleep(50)` 防止 Vue 异步 handler 竞态导致 URL 错位。

**不需要 CDP Input.dispatchMouseEvent**（已废弃）。原生 `.click()` 即可触发完整事件链。

### 滚动加载

无限滚动机制：`window.scrollTo(0, document.body.scrollHeight)` 触发 XHR，每次加载 30-45 篇新文章，追加到 DOM 末尾。滚动必须通过浏览器级 eval 执行（Python CDP WebSocket 的 `Runtime.evaluate` 不会触发 XHR）。

### 去重

每篇文章有唯一 `data-id`（格式 `{msg_id}&{idx}`），用于去重。

## 依赖

- **Windows Edge CDP 浏览器**（debug port 9222，WSL 通过 portproxy 9223 连接）
- **微信读书登录态**（通过扫码登录获得）
- **agent-browser**（CDP 浏览器控制，npm 全局安装）
- **Python 3 + websockets**（URL 批量提取）

完整的前置环境配置见 `wsl-cdp-browser` skill。

## 使用方法

详细操作步骤见 [SKILL.md](./SKILL.md)。

简要用法：

```bash
# 启动 CDP 浏览器（详见 SKILL.md Step 1）
# 扫码登录微信读书（详见 SKILL.md Step 2）

# 搜索关键词并获取文章列表
export PATH="$HOME/.local/bin:$PATH"
WS_URL=$(curl -s "http://172.19.80.1:9223/json/version" | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['webSocketDebuggerUrl'])")

# 导航到搜索页
agent-browser --cdp "$WS_URL" goto \
  "https://search.weixin.qq.com/cgi-bin/newsearchweb/userclientjump?path=page/search/weread&query=关键词&platform=pc"

# 滚动加载全部结果（详见 SKILL.md Step 3）
# 批量提取链接（详见 SKILL.md Step 4）

# 关闭浏览器
/mnt/c/Windows/System32/taskkill.exe /F /IM msedge.exe
```

## 输出格式

搜索完成后输出格式如下：

```
**关键词 公众号文章搜索**

搜到 X 篇 → 提取 Y 篇 → Z 篇有链接（成功率 N%）

🔥 Top 10：

1. [文章标题](http://mp.weixin.qq.com/s/...) — 发布时间
2. [文章标题](http://mp.weixin.qq.com/s/...) — 发布时间
...
```

完整数据（含所有文章元数据和链接）保存在 `/tmp/urls.json`。

## 声明

- 本项目**仅负责搜索公众号文章并获取 `mp.weixin.qq.com` 链接**，不包含抓取文章正文内容的功能
- 需要有效的微信读书登录态（扫码登录），session 过期后需重新扫码
- 部分 `mp.weixin.qq.com` 链接可能返回「参数错误」，这是微信服务端反爬/权限控制，与提取流程无关
