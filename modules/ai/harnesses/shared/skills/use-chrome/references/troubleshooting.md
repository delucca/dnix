# Troubleshooting & Known Limits — use-chrome

Reference this file when Chrome automation fails or behaves unexpectedly.

## Common errors

**"Chrome not reachable at 127.0.0.1:9222"**
Chrome is not running with remote debugging. On the laptop, run `chrome_up` (kickstarts the launchd debug-profile Chrome). Ad-hoc fallback:
```bash
open -a "Google Chrome" --args --remote-debugging-port=9222 --no-first-run
```
Wait ~2 seconds, then retry. If port 9222 is in use by another app, `curl http://127.0.0.1:9222/json/version` reveals what is listening. The response will include a `Browser` field and a `webSocketDebuggerUrl` when Chrome is the listener.

**"npx download is slow on first call"**
chrome-devtools-mcp downloads on first run (~2–5 seconds). Subsequent calls hit the npx cache and start in under a second. On a nix machine nothing downloads: dnix's packaged `chrome-devtools-mcp` on PATH is used directly.

**"evaluate fails or returns nothing"**
`evaluate_script` JSON-serializes the return value, so it must be JSON-serializable — DOM nodes, functions, and circular structures fail. Return scalar properties instead (`el.textContent`, not `el`). Bare expressions are wrapped into `() => ( <expr> )` automatically; pass an arrow function for multi-statement or `async` code.

**"screenshot is blank or shows the wrong page"**
chrome-devtools-mcp targets the *selected page* (see `raw list_pages` / `raw select_page`), which defaults to the first tab. Navigate first to lock in the right page: `$SCRIPT navigate <url>`, then screenshot. If you passed `--url` to screenshot and it still shows the wrong page, the navigate step may have raced with the screenshot — add a `$SCRIPT navigate <url>` call first as a separate step.

**"Connection refused" on a working Chrome installation**
Chrome launched without `--remote-debugging-port=9222`. Quit Chrome fully (Cmd+Q, not just closing the window) and relaunch with the flag. On macOS, closing all windows does not quit the app.

**"MCP error -32601: Method not found"**
The tool name does not exist in this version of chrome-devtools-mcp. Run `$SCRIPT raw --help` and use the `raw` subcommand to call `tools/list` to see what tools are available in the running version.

**"Subprocess exited unexpectedly"**
Check that Chrome is still running and the debug port is still open. Chrome may have been closed or relaunched between the preflight check and the MCP handshake. Run the command again after confirming Chrome is up.

## Known limits

| Limit | Impact | Workaround |
|---|---|---|
| Each skill call spawns a fresh subprocess | State does not persist between calls | Chain navigate+action in one compound invocation using multiple subcommands, or use `raw` for multi-step flows |
| chrome-devtools-mcp targets the selected page (defaults to the first tab) | Screenshots and evaluations may hit the wrong page | Always call `$SCRIPT navigate <url>` first, or `raw select_page` to switch tabs |
| Port 9222 may be occupied by another Chrome profile | Unexpected tab context | `curl http://127.0.0.1:9222/json/version` shows which profile is connected |
| No PDF tool in chrome-devtools-mcp | `$SCRIPT pdf` exits with an error | `screenshot --full-page`, or print from Chrome on the host |
| Native element tools (`click`, `fill`, `hover`, `drag`) take `uid`s, not CSS selectors | Selector-based raw calls fail with schema errors | `raw take_snapshot` first, then pass the element's `uid`; or use the skill's `click`/`fill` subcommands (injected JS, selectors work) |
| `wait_for`, `press_key`, `fill_form`, `emulate` have no convenience wrappers | Requires the `raw` subcommand | `$SCRIPT raw press_key --args '{"key":"Enter"}'` |
| npx caches by version tag | `@latest` tag is resolved once per cache lifetime | Pass an explicit version (e.g. `chrome-devtools-mcp@0.2.0`) to pin if the behavior changes between runs |

## Why no persistent subprocess

The skill terminates the MCP subprocess after each call because keeping it alive across agent turns would require a daemon process, port management, and cleanup hooks — all complexity that exceeds the benefit for typical one-shot browser inspection tasks. For multi-step workflows (fill a form, click submit, screenshot the result), chain the subcommands within a single Bash invocation using `&&`:

```bash
SCRIPT=~/.config/ai/common/skills/use-chrome/scripts/use-chrome.py
$SCRIPT navigate https://example.com && $SCRIPT screenshot
```

Each command spawns its own subprocess, but the browser state (the tab you navigated to) persists in Chrome between calls.
