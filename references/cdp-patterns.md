# CDP Interaction Patterns for WeChat Read Search

## CDP Endpoint Levels

### Browser level (`/json/version`)
- Good for: `Browser.getVersion`, getting initial WS URL for agent-browser
- **Cannot** receive: `Network.*`, `Page.windowOpen`, `Page.frameNavigated` events
- URL: `curl -s http://<WINDOWS_IP>:9223/json/version | jq -r .webSocketDebuggerUrl`

### Page level (`/json` list → page targets)
- **Required** for: all page events, Network interception, Runtime.evaluate
- URL: `curl -s http://<WINDOWS_IP>:9223/json | jq -r '.[] | select(.type=="page" and (.url | contains("search.weixin"))) | .webSocketDebuggerUrl'`

## Key CDP Commands

### Enable domains (MUST do first)
```json
{"id": 1, "method": "Page.enable"}
{"id": 2, "method": "Network.enable"}
```

### Mouse click (for triggering navigation)
WeChat search page requires real mouse events for navigation. JS `element.click()` won't work.

```json
// Get coordinates
{"id": 3, "method": "Runtime.evaluate", "params": {
    "expression": "document.querySelector('.search_list_item .article__title-text').getBoundingClientRect()"
}}
// Response: {x, y, width, height}

// Click
{"id": 4, "method": "Input.dispatchMouseEvent", "params": {
    "type": "mousePressed", "x": <cx>, "y": <cy>, "button": "left", "clickCount": 1
}}
{"id": 5, "method": "Input.dispatchMouseEvent", "params": {
    "type": "mouseReleased", "x": <cx>, "y": <cy>, "button": "left", "clickCount": 1
}}
```

### Catch article URL
After click, listen for:
```json
{"method": "Page.windowOpen", "params": {"url": "https://mp.weixin.qq.com/s?__biz=...&mid=...&idx=...&sn=..."}}
```

## Common Errors

### "Frame with the given frameId is not found"
- Happens when clicking iframe elements via agent-browser before iframe fully renders
- Fix: wait 3-6 seconds and retry

### "Debugger agent is not enabled"
- Happens when calling Debugger.* methods without `Debugger.enable`
- Usually unnecessary; just use Runtime.evaluate instead

### TimeoutError on ws.recv()
- CDP sends events asynchronously; not all messages are responses to your commands
- Use `asyncio.wait_for(ws.recv(), timeout=N)` in a loop
- Filter by checking `data.get('method')` for the event you want
