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

```python
import json
from datetime import datetime

# 读现有数据
with open('~/.hermes/data/topology-optimization-articles.json') as f:
    existing = json.load(f)

seen_ids = set(existing.get('seen_ids', []))

# 新文章 = dataId 不在 seen_ids 中
new_articles = []
for art in merged_results:
    if art['dataId'] and art['dataId'] not in seen_ids:
        new_articles.append(art)
        seen_ids.add(art['dataId'])

# 更新并写回
existing['last_run'] = datetime.now().isoformat()
existing['articles'] = merged_results  # 全量快照
existing['seen_ids'] = list(seen_ids)
with open(path, 'w') as f:
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

- `dataId` 可能为空字符串，空 `dataId` 不做去重（每次都算新）
- `seen_ids` 只增不减——即使文章不再出现在搜索结果中，它的 ID 也永久保留以防止未来重复
- 首次运行时 `seen_ids` 为空，所有文章都会输出为"新"
