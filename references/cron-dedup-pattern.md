# 定时搜索 + 去重持久化模式

适用于定时 cron 作业：搜索公众号关键词 → 提取文章 → 按 `dataId` 去重 → 仅输出新文章。

## JSON 存储格式

文件路径：`~/.hermes/data/<keyword-slug>-articles.json`

```json
{
  "keyword": "拓扑优化",
  "created": "2026-05-18",
  "last_run": "2026-05-18T13:53:00.000000",
  "articles": [
    {
      "title": "文章标题",
      "source": "公众号名",
      "date": "2026-05-16",
      "url": "http://mp.weixin.qq.com/s?...",
      "dataId": "12345678&2"
    }
  ],
  "seen_ids": ["12345678&2", "87654321&2"]
}
```

- `articles`：全量文章快照（每次运行覆盖为最新）
- `seen_ids`：所有曾出现过的 `dataId`（只增不减，用于去重）

## 去重逻辑（Python）

> ⚠️ **两步法（关键）**：先识别新文章 → 保存到临时文件 → 再更新 JSON。**不要在同一段代码里同时识别和更新**，否则更新后 seen_ids 已变，无法再读回格式化输出。

```python
import json, os
from datetime import datetime

DATA_FILE = os.path.expanduser('~/.hermes/data/topology-optimization-articles.json')

# ── 第一步：识别新文章，写出到临时文件 ──
with open(DATA_FILE) as f:
    existing = json.load(f)

seen_ids = set(existing.get('seen_ids', []))

new_articles = []
for art in merged_results:
    if art['dataId'] and art['dataId'] not in seen_ids:
        new_articles.append(art)

# 先保存新文章列表到临时文件（格式化输出从这里读）
with open('/tmp/new_articles.json', 'w') as f:
    json.dump(new_articles, f, ensure_ascii=False)

print(f"New articles: {len(new_articles)}")

# ── 第二步：更新持久化文件（此时可安全覆盖）──
for art in new_articles:
    seen_ids.add(art['dataId'])

existing['last_run'] = datetime.now().isoformat()
existing['articles'] = merged_results  # 全量快照
existing['seen_ids'] = list(seen_ids)

with open(DATA_FILE, 'w') as f:
    json.dump(existing, f, ensure_ascii=False, indent=2)
```

## 输出格式

```
**🔍 <关键词> · 今日新文章**
搜到 N 篇 → 其中 M 篇为新（首次发现）

1. [标题](url) — 来源 · 日期
2. ...

> 📁 历史归档：~/.hermes/data/<keyword>-articles.json（累计 X 篇）
```

如果没有新文章：
```
🔍 <关键词> · 今日无新文章（共搜到 N 篇）
```

## 注意事项

- **两步法（关键）**：先识别新文章并写入 `/tmp/new_articles.json`，再更新持久化 JSON。如果先更新 JSON（seen_ids 已变），后续无法区分新旧。
- `dataId` 可能为空字符串，空 `dataId` 不做去重（每次都算新）
- `seen_ids` 只增不减——即使文章不再出现在搜索结果中，它的 ID 也永久保留以防止未来重复
- 首次运行时 `seen_ids` 为空，所有文章都会输出为"新"
- 格式化输出时从 `/tmp/new_articles.json` 读取，不要重新读持久化 JSON（seen_ids 已更新）
- **🔴 输出格式化必须用 execute_code 从 JSON 读 URL**：terminal 输出会截断长 URL（丢失 chksm/#rd 导致"参数错误"）。用 execute_code 中 Python `json.load()` + `print()` 构建最终消息，markdown 链接 `[title](url)` 中的 URL 从 JSON 对象直接取（不经控制台截断）。**严禁从 execute_code 或 terminal 的输出中复制 URL。**
