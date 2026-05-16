#!/usr/bin/env python3
"""
微信读书搜索 - 通过微信读书搜索微信公众号文章
⚠️ 备用/调试工具，非主流程。主流程应使用 agent-browser --cdp 命令。

需要：Windows Edge CDP 已启动（debug port 9222, portproxy 9223）
     微信读书已登录
     搜索页面已经在浏览器中打开（可用 agent-browser 先导航）

Usage:
  python search_weread.py "关键词" -n 100 --json
"""

import asyncio
import json
import subprocess
import sys
import argparse
from urllib.parse import quote

WINDOWS_IP = "172.19.80.1"
CDP_PORT = 9223

def get_search_page_ws():
    """获取搜索页面的 WebSocket URL"""
    result = subprocess.run(
        ['curl', '-s', f'http://{WINDOWS_IP}:{CDP_PORT}/json'],
        capture_output=True, text=True
    )
    targets = json.loads(result.stdout)
    for t in targets:
        if t['type'] == 'page' and 'search.weixin' in t.get('url', ''):
            return t['webSocketDebuggerUrl'], t['id']
    for t in targets:
        if t['type'] == 'page':
            return t['webSocketDebuggerUrl'], t['id']
    raise RuntimeError("No page target found")


async def get_article_count(ws):
    await ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate', 'params': {
        'expression': 'document.querySelectorAll(".search_list_item").length'
    }}))
    try:
        msg = await asyncio.wait_for(ws.recv(), timeout=3)
        data = json.loads(msg)
        return data.get('result', {}).get('result', {}).get('value', 0)
    except:
        return 0


async def wait_for_results(ws, timeout=15):
    for _ in range(timeout):
        count = await get_article_count(ws)
        if count > 0:
            return count
        await asyncio.sleep(1)
    return 0


async def extract_articles_data(ws):
    js_expr = """
    (function() {
        const articles = [];
        document.querySelectorAll('.search_list_item').forEach((item, i) => {
            const t = item.querySelector('.article__title-text');
            const d = item.querySelector('.article__desc');
            const th = item.querySelector('.article__thumb');
            const s = item.querySelector('.source__title');
            const dt = item.querySelector('.source__text.date');
            articles.push({
                idx: i,
                title: (t?.textContent || '').trim(),
                desc: (d?.textContent || '').trim(),
                thumb: th?.getAttribute('data-thumb-url') || '',
                source: (s?.textContent || '').trim(),
                date: (dt?.textContent || '').trim(),
                dataId: item.getAttribute('data-id') || ''
            });
        });
        return articles;
    })()
    """
    await ws.send(json.dumps({'id': 2, 'method': 'Runtime.evaluate', 'params': {
        'expression': js_expr, 'returnByValue': True
    }}))
    try:
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        data = json.loads(msg)
        return data.get('result', {}).get('result', {}).get('value', [])
    except:
        return []


async def click_get_url(ws, idx):
    pos_js = (
        "(function() {"
        " const els = document.querySelectorAll('.search_list_item .article__title-text');"
        f" const el = els[{idx}];"
        " if (!el) return null;"
        " const r = el.getBoundingClientRect();"
        " return {x: r.left + r.width/2, y: r.top + r.height/2};"
        "})()"
    )
    await ws.send(json.dumps({'id': 3, 'method': 'Runtime.evaluate', 'params': {'expression': pos_js}}))
    try:
        msg = await asyncio.wait_for(ws.recv(), timeout=3)
        pos = json.loads(msg).get('result', {}).get('result', {}).get('value')
        if not pos:
            return None
    except:
        return None
    
    await ws.send(json.dumps({'id': 4, 'method': 'Input.dispatchMouseEvent', 'params': {
        'type': 'mousePressed', 'x': pos['x'], 'y': pos['y'], 'button': 'left', 'clickCount': 1
    }}))
    await ws.send(json.dumps({'id': 5, 'method': 'Input.dispatchMouseEvent', 'params': {
        'type': 'mouseReleased', 'x': pos['x'], 'y': pos['y'], 'button': 'left', 'clickCount': 1
    }}))
    
    for _ in range(25):
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
            data = json.loads(msg)
            if data.get('method') == 'Page.windowOpen':
                return data['params']['url']
        except asyncio.TimeoutError:
            break
    return None


async def scroll_for_more(ws):
    for _ in range(3):
        await ws.send(json.dumps({'id': 6, 'method': 'Runtime.evaluate', 'params': {
            'expression': 'window.scrollTo(0, document.body.scrollHeight)'
        }}))
        await asyncio.sleep(2)
    await asyncio.sleep(2)
    return await get_article_count(ws)


async def search_and_extract(query, target_count=100, max_scrolls=20):
    import websockets
    
    ws_url, tab_id = get_search_page_ws()
    print(f"[*] Tab: {tab_id[:8]}", file=sys.stderr)
    
    async with websockets.connect(ws_url, max_size=2**24) as ws:
        await ws.send(json.dumps({'id': 0, 'method': 'Page.enable'}))
        await asyncio.sleep(0.3)
        
        count = await get_article_count(ws)
        if count == 0:
            print(f"[*] Navigating to search...", file=sys.stderr)
            url = f"https://search.weixin.qq.com/cgi-bin/newsearchweb/userclientjump?path=page/search/weread&query={quote(query)}&platform=pc"
            await ws.send(json.dumps({'id': 7, 'method': 'Page.navigate', 'params': {'url': url}}))
            count = await wait_for_results(ws)
        
        print(f"[*] Articles visible: {count}", file=sys.stderr)
        
        if count == 0:
            print("[!] No results. Check login or query.", file=sys.stderr)
            return []
        
        all_articles = []
        seen_ids = set()
        scroll_count = 0
        
        while len(all_articles) < target_count and scroll_count <= max_scrolls:
            articles = await extract_articles_data(ws)
            new_articles = [a for a in articles if a['dataId'] not in seen_ids]
            
            if not new_articles:
                if scroll_count > 0:
                    break
                # First time with no new articles but we have some - might be all dups
                if len(articles) > 0:
                    print(f"[!] All {len(articles)} articles already seen", file=sys.stderr)
                break
            else:
                print(f"[*] {len(new_articles)} new articles", file=sys.stderr)
            
            for article in new_articles:
                if len(all_articles) >= target_count:
                    break
                if article['dataId'] in seen_ids:
                    continue
                
                url = await click_get_url(ws, article['idx'])
                article['url'] = url or ''
                seen_ids.add(article['dataId'])
                del article['dataId']
                del article['idx']
                
                all_articles.append(article)
                s = '✓' if url else '✗'
                print(f"  {s} [{len(all_articles)}] {article['title'][:55]}", file=sys.stderr)
                
                await asyncio.sleep(0.4)
            
            if len(all_articles) >= target_count:
                break
            
            scroll_count += 1
            if scroll_count <= max_scrolls:
                print(f"[*] Scrolling {scroll_count}/{max_scrolls}...", file=sys.stderr)
                new_count = await scroll_for_more(ws)
                print(f"[*] Now {new_count} visible", file=sys.stderr)
        
        return all_articles[:target_count]


def main():
    parser = argparse.ArgumentParser(description='微信读书公众号文章搜索')
    parser.add_argument('query', help='搜索关键词')
    parser.add_argument('-n', '--count', type=int, default=100, help='目标数量 (默认: 100)')
    parser.add_argument('--json', action='store_true', help='JSON 输出')
    args = parser.parse_args()
    
    result = asyncio.run(search_and_extract(args.query, args.count))
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for i, a in enumerate(result, 1):
            print(f"\n{'='*60}")
            print(f"[{i}] {a['title']}")
            print(f"  公众号: {a['source']}")
            print(f"  时间: {a['date']}")
            print(f"  链接: {a['url']}")
            print(f"  简介: {a['desc'][:120]}...")


if __name__ == '__main__':
    main()
