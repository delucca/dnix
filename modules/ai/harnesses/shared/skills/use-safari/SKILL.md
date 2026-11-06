---
name: use-safari
description: Drives the user's running Safari and its sign-ins via Apple Events, for tabs, JS, clicks, forms and screenshots. Use when the user names Safari or a site only works there. NOT for Chrome (use-chrome).
argument-hint: "[tabs|navigate|evaluate|text|source|click|fill|wait|copy|screenshot|close] [args]"
allowed-tools: Bash(python3 */use-safari/scripts/safari.py *), Read
compatibility: Requires macOS with Safari, python3, and the built-in osascript and screencapture.
---

# Use Safari

Drive the Safari the user already has open, with their own profile and sign-ins, through Apple Events. There is no debug profile, second browser or MCP server: one standard-library Python script asks `osascript` to run JavaScript in a tab through Safari's `do JavaScript`.

Route `$ARGUMENTS` to a subcommand, or carry out the described browser task with the workflow below.

## When to use it

- The user names Safari, or a site lets only Safari through (a device-bound sign-in such as Okta FastPass that the Chrome debug profile cannot pass).
- Otherwise prefer `use-chrome`: its debug profile keeps the agent away from the user's own browsing.

## Setup

This works on macOS only. It needs `python3` plus the built-in `osascript` and `screencapture`, so there is nothing to install. Once per Mac, the user turns on Safari Settings > Advanced > "Show features for web developers", then Develop > "Allow JavaScript from Apple Events". The first call also raises the macOS Automation prompt for the app running the shell, and the user approves it there. When a step is missing, the script names the step that is missing. Never change these settings yourself.

```bash
python3 {baseDir}/scripts/safari.py tabs
```

## Commands

```bash
python3 {baseDir}/scripts/safari.py tabs [--full]
python3 {baseDir}/scripts/safari.py navigate URL [--tab T] [--timeout 20]
python3 {baseDir}/scripts/safari.py evaluate 'JS' [--tab T] [--timeout 30]
python3 {baseDir}/scripts/safari.py text [--selector CSS] [--redact] [--tab T]
python3 {baseDir}/scripts/safari.py source [--tab T]
python3 {baseDir}/scripts/safari.py click [CSS|XPATH] [--text 'Visible text'] [--nth N] [--tab T]
python3 {baseDir}/scripts/safari.py fill CSS 'value' [--tab T]
python3 {baseDir}/scripts/safari.py wait [--selector CSS [--gone] | --text 'words'] [--timeout 20] [--tab T]
python3 {baseDir}/scripts/safari.py copy --from T --to T (--selector CSS | --js 'JS') --field CSS
python3 {baseDir}/scripts/safari.py screenshot [--tab T] [--output PATH]
python3 {baseDir}/scripts/safari.py close --tab T
```

**Targeting.** `--tab` takes the `window:tab` id that `tabs` and `navigate` print (`15100:3`), or a case-insensitive URL or title substring that matches exactly one tab across all windows. Without `--tab`, a command acts on the front window's current tab, which is the page the user is looking at. Once you have an id, pass it: it stays valid until a tab to its left closes.

- `tabs` lists every window's tabs, front window first, `*` marking each window's current tab. URLs drop their query and fragment unless `--full`, because callback URLs carry tokens.
- `navigate` opens the URL in a new tab of the front window, or loads it in place with `--tab`. It waits for the new page to load and prints `id  title  url`.
- `evaluate` wraps a bare expression as `() => (expr)`. For statements, pass a function: `'() => { const n = 2; return n * 2 }'`. It awaits promises, so `fetch` works with the user's session. Results must be JSON-serializable, and strings print raw.
- `text` prints `innerText` of the page or of `--selector`. Add `--redact` on pages that display keys.
- `source` saves the rendered DOM to a file and prints its path.
- `click` takes a CSS selector, an XPath (starting with `/`), `--text`, or a selector plus `--text`. Text matching searches clickable elements, exact match first, then substring. When several elements match, it refuses and lists them; rerun with `--nth`. It dispatches pointer and mouse events before `click()`, so menus that open on `pointerdown` respond.
- `fill` sets the value through the native setter and fires `input` and `change`, so React and Vue state sees it. It refuses a selector that matches several elements or something that is not a field.
- `wait` polls until the selector appears (or, with `--gone`, disappears), the text shows up, or with neither flag, the page finishes loading. Use it instead of `sleep`.
- `copy` reads a value in one tab and writes it into a field in another within a single `osascript` run. It prints only the length and, for values of 16 or more characters, the first four. Move every secret this way, such as a freshly generated API key, so it never enters the transcript.
- `screenshot` brings the tab's window to the front for about a second, because macOS cannot capture a background or Stage Manager window. It captures the visible viewport, not the full page, and gives focus back to the previous app. Open the saved PNG to look at it.
- `close` closes one tab and requires `--tab`.

## Working in the user's browser

Every site the user is signed into acts on their behalf here, so:

1. Work in tabs you open with `navigate`. Do not navigate, reload or close a tab you did not open unless the user asks.
2. Before acting, confirm the page and account with `text` or `evaluate`, since the user may have several accounts signed in.
3. Ask before anything that sends, submits, pays, deletes or changes account settings, unless the user asked for that exact action.
4. Close the tabs you opened when the task is done.

## Output

Short results print inline. Long text spills to `~/.cache/safari-cm/` with a preview and the file path, and screenshots and page sources are saved there too. Errors go to stderr with exit status 1.

## Troubleshooting

When a call fails or hangs, read `{baseDir}/references/troubleshooting.md`. It covers the setup errors, Automation denials, page dialogs that block Apple Events, parse errors hidden by the wrapper, and screenshot failures.

## Hard prohibitions

- Never print a password, token, cookie or API key. Use `copy` to move one and `text --redact` to read around one.
- Never quit Safari, close the user's own windows or tabs, or change Safari or macOS settings.
- Never submit, send, buy or delete without the user's go-ahead for that action.
