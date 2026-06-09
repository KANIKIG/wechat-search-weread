# CDP 滚动事件不触发问题

> **发现日期**: 2026-06-09  
> **影响范围**: 所有依赖 scroll 事件触发 XHR 的页面（含微信搜一搜无限滚动）

## 问题

某些 CDP 实现下，**任何形式的程序化滚动都不会触发 `scroll` 事件**，即使 `scrollY` 确实改变了。

## 验证方法

在目标页面注册 scroll 事件监听器，然后用不同方式滚动并检查事件计数：

```bash
# 注册监听
agent-browser eval "window.__sc=0;window.addEventListener('scroll',()=>{window.__sc++});'ok'"

# 测试方式1: window.scrollTo
agent-browser eval "window.scrollTo(0,500)"
sleep 2
agent-browser eval "window.__sc"  # → 0

# 测试方式2: scrollIntoView
agent-browser eval "document.querySelector('.search_list_item:last-child').scrollIntoView({block:'end'})"
sleep 2
agent-browser eval "window.__sc"  # → 0

# 测试方式3: agent-browser scroll
agent-browser scroll down 800
sleep 2
agent-browser eval "window.__sc"  # → 0

# 测试方式4: PageDown 键
agent-browser press PageDown
sleep 2
agent-browser eval "window.__sc"  # → 0
```

## 确认结果

| 方式 | scrollY 改变？ | scroll 事件触发？ |
|------|:---:|:---:|
| `window.scrollTo()` | ✅ | ❌ |
| `scrollIntoView()` | ✅ | ❌ |
| `agent-browser scroll down` | ✅ | ❌ |
| `agent-browser press PageDown` | ✅ | ❌ |

> 重启浏览器、更换 user-data-dir 均无效。这是 CDP 实现层面的问题。

## 对微信搜一搜的影响

微信搜一搜搜索页的无限滚动机制依赖于 `scroll` 事件 → XHR 加载更多文章。`scroll` 事件不触发 ⇒ XHR 永远不发出 ⇒ 文章数永远停在初始的 **15 篇**。

> ⚠️ 页面 body 中「加载中」字样是**静态模板文本**，不是实时加载指示器。不能据此判断滚动是否工作。

## 解决方案

**首选：每次 scrollTo 后手动 `window.dispatchEvent(new Event('scroll'))`**。已在 detailed-workflow.md Step 3.2 的滚动循环中实现，实测可用。

如果上述方案仍不生效，可换用其他浏览器 CDP（如 Chrome）。Chrome 的 CDP 实现中 scroll 事件正常触发。启动方式见 wsl-cdp-browser.md。

## 已知无法使用的替代方案

- `Runtime.evaluate` 执行 `window.scrollTo`：不触发 XHR（本来就是如此，见 detailed-workflow.md）
- CDP `Input.dispatchMouseEvent` (mouseWheel)：CDP 下同样不触发 scroll 事件
- `agent-browser scroll` 命令：底层也是 CDP，同样不触发
