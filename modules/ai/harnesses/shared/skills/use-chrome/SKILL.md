---
name: use-chrome
description: Automates a running Chrome browser for screenshots, JS eval and clicks. Use for screenshot a URL, browser automation. NOT for headless scraping.
argument-hint: "[screenshot|navigate|evaluate|source|pdf|click|fill|cookies|raw] [args]"
allowed-tools: Bash(python3 *), Bash(*/use-chrome/scripts/use-chrome.py *), Bash(mkdir -p /tmp/chrome-cm-*), Bash(ls /tmp/chrome-cm-*/*), Read
---

# use-chrome — on-demand Chrome automation via chrome-devtools-mcp

Control a running Chrome browser without keeping the MCP registered permanently. The wrapper spawns `chrome-devtools-mcp` as a short-lived stdio subprocess, runs one or more tool calls, then terminates it. The main agent context stays clean.

## When NOT to use this skill

- Chrome is not running with remote debugging enabled on port 9222 — the skill detects this and prints the start command rather than hanging.
- Headless scraping without a running browser — use an installed scraping skill, if one is listed, or a plain fetch.
- Server-side JS that doesn't need a browser — use `Bash` (node/python) directly.

**Why this design.** Installing chrome-devtools-mcp via `~/.claude.json` injects its tool schemas into every conversation — even when you never touch a browser. This skill loads nothing until you invoke it, and cleans up immediately after.

**Prerequisite.** Chrome must be reachable on `127.0.0.1:9222`. If the preflight check fails, the script prints the exact command to start it. The script will never hang waiting for Chrome.

## Start Chrome with remote debugging

On the laptop, the canonical way is the `chrome_up` command — it kickstarts the launchd-managed debug-profile Chrome (`com.chrome-devtools.browser`) and waits for the port:

```bash
chrome_up
```

Ad-hoc fallback (any Chrome, no launchd):

```bash
open -a "Google Chrome" --args --remote-debugging-port=9222 --no-first-run
```

Verify it is ready: `curl -s http://127.0.0.1:9222/json/version` should return a JSON object with `"Browser"`, `"webSocketDebuggerUrl"`, etc.

## Usage

All subcommands run through one script:

```bash
SCRIPT={baseDir}/scripts/use-chrome.py
$SCRIPT <subcommand> [args]
```

### Screenshot

```bash
$SCRIPT screenshot                         # screenshot current tab
$SCRIPT screenshot --url https://example.com
$SCRIPT screenshot --url https://example.com --full-page
$SCRIPT screenshot --output /tmp/my-page.png
```

The image is saved to `/tmp/chrome-cm-<uid>/<timestamp>-screenshot.png`. After saving, read the file path with the `Read` tool so the agent can see the image (Claude is multimodal — always do this step).

### Navigate

```bash
$SCRIPT navigate https://example.com      # returns page title + current URL
```

### Evaluate JS

```bash
$SCRIPT evaluate "document.title"
$SCRIPT evaluate "window.location.href"
$SCRIPT evaluate "() => { return document.querySelectorAll('a').length; }"
```

Bare expressions are wrapped into `() => ( <expr> )` automatically; arrow/`function` declarations pass through as-is (handy for multi-statement or `async` code). Return values must be JSON-serializable — the MCP serializes them to JSON.

### Get page source

```bash
$SCRIPT source                            # current tab's HTML
$SCRIPT source --url https://example.com
```

Large sources are saved to `/tmp/chrome-cm-<uid>/<timestamp>-source.html` and the path is printed.

### Print to PDF — not supported

chrome-devtools-mcp exposes no PDF tool; `$SCRIPT pdf` exits with an explanatory error. Use `screenshot --full-page` instead, or print from Chrome on the host.

### Click an element

```bash
$SCRIPT click "#submit-button"
$SCRIPT click "button[type=submit]"       # CSS selector
$SCRIPT click "//button[@type='submit']"  # XPath
```

Implemented via injected JS (`querySelector` / `document.evaluate`), so plain selectors work. The MCP's native `click` tool instead takes `uid`s from `take_snapshot` — use `raw` for that flow.

### Fill a form field

```bash
$SCRIPT fill "#email" "user@example.com"
$SCRIPT fill "input[name=query]" "search term"
```

Sets `.value` and dispatches `input`/`change` events via injected JS. For React-style controlled inputs that resist this, use the native uid-based flow: `raw take_snapshot` then `raw fill --args '{"uid":"...","value":"..."}'`.

### Get cookies

```bash
$SCRIPT cookies                           # current tab
$SCRIPT cookies --url https://example.com
```

Reads `document.cookie` — HttpOnly cookies are not visible.

### Escape hatch

Any tool exposed by chrome-devtools-mcp is reachable via `raw`:

```bash
$SCRIPT raw navigate_page --args '{"type":"url","url":"https://example.com"}'
$SCRIPT raw evaluate_script --args '{"function":"() => document.querySelector(\"h1\").textContent"}'
$SCRIPT raw take_snapshot                 # a11y tree with element uids
$SCRIPT raw click --args '{"uid":"<uid from take_snapshot>"}'
$SCRIPT raw hover --args '{"uid":"<uid from take_snapshot>"}'
$SCRIPT raw press_key --args '{"key":"Enter"}'
$SCRIPT raw list_pages
$SCRIPT raw new_page --args '{"url":"https://example.com"}'
```

Element tools (`click`, `fill`, `hover`, `drag`, `upload_file`) take `uid`s from `take_snapshot`, not CSS selectors. Other available tools: `wait_for`, `fill_form`, `emulate`, `resize_page`, `select_page`, `close_page`, `handle_dialog`, `list_console_messages`, `list_network_requests`, `performance_*`, `lighthouse_audit`, `take_heapsnapshot`. Full schemas via `tools/list` over the stdio MCP connection.

## Screenshot workflow (most common)

When the user asks to "check what this page looks like" or "take a screenshot of URL":

1. Run `{baseDir}/scripts/use-chrome.py screenshot --url <url>`
2. The script prints the saved path, e.g. `/tmp/chrome-cm-<uid>/20260526-120000-screenshot.png`
3. Read that path with the `Read` tool — Claude renders the image inline.
4. Describe what you see.

## Output handling

- Short results (≤4 KB text) print to stdout.
- Images save to `/tmp/chrome-cm-<uid>/<timestamp>-screenshot.png` (base64 decoded from MCP response).
- Large text (source, large JSON) saves to `/tmp/chrome-cm-<uid>/<timestamp>-<op>.html|json` — the path is printed.
- Read image and large-text paths with the `Read` tool to display them.

## Troubleshooting and limits

When something fails — wrong tab, blank screenshot, connection refused, slow npx — read the reference file for diagnosis steps and workarounds:

```
Read({baseDir}/references/troubleshooting.md)
```

The most common failure is Chrome not running with `--remote-debugging-port=9222`. The script's preflight check catches this immediately and prints the start command.

## Design notes

**No persistent subprocess.** The MCP subprocess terminates after each call to keep the agent environment clean. Browser state (the tab you navigated to) persists in Chrome between calls, so chaining subcommands with `&&` works:

```bash
{baseDir}/scripts/use-chrome.py navigate https://example.com && \
{baseDir}/scripts/use-chrome.py screenshot
```

**No `--slim` flag.** The full chrome-devtools-mcp tool surface is exposed. Passing `--slim` would hide several tools (hover, drag, performance tools) without benefit since the subprocess is ephemeral and its schemas never enter the main agent context.

**Screenshots go to `/tmp/chrome-cm-<uid>/`.** This path is predictable and consistent across calls. Saving elsewhere risks cluttering the working tree. The `--output` flag is the right override for one-off destinations.

**Preflight exit on failure.** The script exits immediately when Chrome is unreachable rather than waiting for a timeout. Hanging on a bad connection would freeze the agent turn.
