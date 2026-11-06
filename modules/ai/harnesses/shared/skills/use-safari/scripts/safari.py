#!/usr/bin/env python3
"""Drive the user's running Safari through Apple Events (do JavaScript).

Usage: safari.py <subcommand> [args]
       safari.py <subcommand> --help
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from emit import emit_to, secure_cache_dir  # noqa: E402

RUNNER = Path(__file__).with_name("safari.js")
CALL_TIMEOUT = 30
POLL = 0.3
# Stage Manager animates a raised window back to full size; capturing earlier fails.
RAISE_DELAY = 1.0
PLACEHOLDER = "__USE_SAFARI_VALUE__"
CLICKABLE = ", ".join([
    "button", "a", "summary", "label", "input[type=submit]", "input[type=button]",
    "[role=button]", "[role=link]", "[role=tab]", "[role=menuitem]", "[role=option]",
    "[role=checkbox]", "[role=switch]",
])

SETUP_HINT = (
    "Safari refuses scripts from Apple Events. In Safari, open Settings > Advanced, tick "
    "'Show features for web developers', then enable Develop > 'Allow JavaScript from Apple Events'."
)
AUTOMATION_HINT = (
    "macOS blocked Apple Events to Safari. Allow the app running this shell under System Settings > "
    "Privacy & Security > Automation > Safari, then retry."
)


class SafariError(Exception):
    pass


class NoResult(SafariError):
    pass


def out_dir() -> Path:
    return secure_cache_dir("safari")


def apple_events_js_enabled() -> bool | None:
    try:
        proc = subprocess.run(
            ["defaults", "read", "com.apple.Safari", "AllowJavaScriptFromAppleEvents"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return False
    return proc.stdout.strip() == "1"


def diagnose(message: str, code, js: bool) -> str:
    if code == -1743 or "Not authorized to send Apple events" in message:
        return f"{message}\n{AUTOMATION_HINT}"
    if js and apple_events_js_enabled() is False:
        return f"{message}\n{SETUP_HINT}"
    return message


def call(op: str, js: bool = False, **req) -> dict:
    req["op"] = op
    try:
        proc = subprocess.run(
            ["osascript", "-l", "JavaScript", str(RUNNER)],
            input=json.dumps(req), capture_output=True, text=True, timeout=CALL_TIMEOUT,
        )
    except FileNotFoundError:
        raise SafariError("osascript is missing; use-safari runs only on macOS")
    except subprocess.TimeoutExpired:
        raise SafariError(
            f"Safari did not answer within {CALL_TIMEOUT}s. A page dialog (alert, confirm, a sign-in "
            "sheet) blocks Apple Events until someone dismisses it; ask the user to check Safari."
        )
    if proc.returncode != 0:
        raise SafariError(diagnose(proc.stderr.strip() or f"osascript exited {proc.returncode}", None, js))
    try:
        reply = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise SafariError(f"unexpected reply from osascript: {proc.stdout[:200]!r}")
    if not reply.get("ok"):
        error = reply.get("error") or "unknown error"
        raise SafariError(diagnose(error, reply.get("code"), js and reply.get("appleEvent", False)))
    return reply


# ── page code ────────────────────────────────────────────────────────────────

FUNC_RE = re.compile(r"^\s*(async\s+)?(function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)")

ENVELOPE = """(() => {
  const ok = v => JSON.stringify({ok: true, v: v === undefined ? null : v});
  const err = e => JSON.stringify({ok: false, error: String(e && e.message || e)});
  try {
    const r = (__BODY__)();
    if (r && typeof r.then === "function") {
      const k = "p" + Date.now().toString(36) + Math.random().toString(36).slice(2);
      const box = (window.__useSafari = window.__useSafari || {});
      box[k] = null;
      r.then(v => { try { box[k] = ok(v); } catch (e) { box[k] = err(e); } }, e => { box[k] = err(e); });
      return JSON.stringify({pending: k});
    }
    return ok(r);
  } catch (e) {
    return err(e);
  }
})()"""

SETTLE = """(() => {
  const box = window.__useSafari || {};
  const k = __KEY__;
  if (!(k in box)) return JSON.stringify({ok: false, error: "the page navigated before the promise settled"});
  if (box[k] === null) return JSON.stringify({pending: k});
  const v = box[k];
  delete box[k];
  return v;
})()"""

FIND = """const find = sel => {
    if (/^\\(?\\.?\\//.test(sel)) {
      const r = document.evaluate(sel, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      return Array.from({length: r.snapshotLength}, (_, i) => r.snapshotItem(i));
    }
    return Array.from(document.querySelectorAll(sel));
  };"""

CLICK = """() => {
  __FIND__
  const sel = __SEL__, text = __TEXT__, nth = __NTH__;
  const label = e => (e.innerText || e.value || e.getAttribute("aria-label") || e.title || "").trim().replace(/\\s+/g, " ");
  const desc = e => e.tagName.toLowerCase() + (e.id ? "#" + e.id : "") + ' "' + label(e).slice(0, 60) + '"';
  let els = find(sel);
  if (text !== null) {
    const exact = els.filter(e => label(e) === text);
    els = exact.length ? exact : els.filter(e => label(e).includes(text));
    els = els.filter(e => !els.some(o => o !== e && e.contains(o)));
  }
  const shown = els.filter(e => e.getClientRects().length > 0);
  if (shown.length) els = shown;
  if (!els.length) return {error: "no element matches"};
  if (nth === null && els.length > 1) return {error: els.length + " elements match; pass --nth", candidates: els.slice(0, 10).map(desc)};
  const el = els[(nth || 1) - 1];
  if (!el) return {error: "--nth " + nth + " is past the " + els.length + " matches"};
  el.scrollIntoView({block: "center"});
  const o = {bubbles: true, cancelable: true, composed: true, view: window, button: 0};
  const p = Object.assign({pointerType: "mouse", isPrimary: true}, o);
  el.dispatchEvent(new PointerEvent("pointerdown", p));
  el.dispatchEvent(new MouseEvent("mousedown", o));
  el.dispatchEvent(new PointerEvent("pointerup", p));
  el.dispatchEvent(new MouseEvent("mouseup", o));
  el.click();
  return {clicked: desc(el)};
}"""

FILL = """() => {
  __FIND__
  const els = find(__SEL__);
  if (!els.length) return {error: "no element matches"};
  if (els.length > 1) return {error: els.length + " elements match; make the selector unique"};
  const el = els[0], value = __VALUE__;
  el.focus();
  if (el.isContentEditable) {
    el.textContent = value;
    el.dispatchEvent(new InputEvent("input", {bubbles: true}));
    return {filled: el.textContent.length};
  }
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
    : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype
    : el instanceof HTMLInputElement ? HTMLInputElement.prototype : null;
  if (!proto) return {error: el.tagName.toLowerCase() + " is not a form field"};
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
  el.dispatchEvent(new Event("input", {bubbles: true}));
  el.dispatchEvent(new Event("change", {bubbles: true}));
  return {filled: String(el.value).length};
}"""

READ_VALUE = """() => {
  __FIND__
  const el = find(__SEL__)[0];
  if (!el) throw new Error("no element matches");
  const field = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement;
  return (field ? el.value : el.innerText).trim();
}"""

TEXT = """() => {
  __FIND__
  const el = __SEL__ === null ? document.body : find(__SEL__)[0];
  if (!el) return {error: "no element matches"};
  const t = el.innerText;
  return {text: __REDACT__ ? t.replace(/[A-Za-z0-9_\\-]{24,}/g, "<redacted>") : t};
}"""

WAIT = {
    "selector": "() => { __FIND__ return find(__SEL__).length > 0 }",
    "gone": "() => { __FIND__ return find(__SEL__).length === 0 }",
    "text": "() => document.body !== null && document.body.innerText.includes(__TEXT__)",
    "load": '() => document.readyState === "complete"',
}

MARK = "() => { window.__useSafariNav = true; return true; }"
LOADED = '() => !window.__useSafariNav && document.readyState === "complete" && location.href !== "about:blank"'


def fill_template(template: str, **values) -> str:
    code = template.replace("__FIND__", FIND)
    for key, value in values.items():
        code = code.replace(f"__{key}__", value)
    return code


def as_function(code: str) -> str:
    return code if FUNC_RE.match(code) else f"() => ({code}\n)"


def envelope(body: str) -> str:
    return ENVELOPE.replace("__BODY__", body)


def parse_env(raw) -> dict:
    if raw is None:
        raise NoResult(
            "no result: the code did not parse, or this tab cannot run scripts (a blank or start page)"
        )
    try:
        env = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise SafariError(f"unexpected page reply: {str(raw)[:200]!r}")
    return env


def run_js(tab: str | None, body: str, timeout: float = 30.0):
    reply = call("js", js=True, tab=tab, code=envelope(body))
    tab_id = reply["tab"]
    env = parse_env(reply.get("result"))
    deadline = time.monotonic() + timeout
    while "pending" in env:
        if time.monotonic() > deadline:
            raise SafariError(f"the promise did not settle within {timeout:g}s")
        time.sleep(POLL)
        probe = SETTLE.replace("__KEY__", json.dumps(env["pending"]))
        env = parse_env(call("js", js=True, tab=tab_id, code=probe).get("result"))
    if not env.get("ok"):
        raise SafariError(f"page error: {env.get('error')}")
    return tab_id, env.get("v")


def op_result(value) -> dict:
    if isinstance(value, dict) and value.get("error"):
        message = value["error"]
        if value.get("candidates"):
            message += "\n" + "\n".join(f"  {i}. {c}" for i, c in enumerate(value["candidates"], 1))
        raise SafariError(message)
    return value


def poll(tab: str, body: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        try:
            if run_js(tab, body, timeout=CALL_TIMEOUT)[1] is True:
                return True
        except NoResult:
            pass
        if time.monotonic() > deadline:
            return False
        time.sleep(POLL)


def emit(label: str, payload, raw_text: bool = False) -> None:
    emit_to(out_dir(), label, payload, raw_text=raw_text)


# ── subcommands ──────────────────────────────────────────────────────────────

def short_url(url: str) -> str:
    return re.split(r"[?#]", url, maxsplit=1)[0]


def cmd_tabs(args) -> None:
    windows = call("tabs")["windows"]
    lines = []
    for w in windows:
        for t in w["tabs"]:
            url = t["url"] if args.full else short_url(t["url"])
            title = t["title"] if len(t["title"]) <= 60 else t["title"][:59] + "…"
            lines.append(f"{w['id']}:{t['index']}  {'*' if t['current'] else ' '} {title}  {url}")
    emit("tabs", "\n".join(lines) or "(no browser windows)", raw_text=True)


def cmd_navigate(args) -> None:
    url = args.url if re.match(r"^[a-z][a-z0-9+.-]*:", args.url, re.I) else f"https://{args.url}"
    if args.tab:
        target, _ = run_js(args.tab, MARK)
        tab_id = call("navigate", tab=target, url=url)["tab"]
    else:
        tab_id = call("navigate", url=url)["tab"]
    loaded = poll(tab_id, LOADED, args.timeout)
    info = call("info", tab=tab_id)
    note = "" if loaded else f"  (still loading after {args.timeout:g}s)"
    print(f"{info['tab']}  {info['title']}  {info['url']}{note}")


def cmd_evaluate(args) -> None:
    _, value = run_js(args.tab, as_function(args.code), timeout=args.timeout)
    emit("evaluate", value, raw_text=isinstance(value, str))


def cmd_text(args) -> None:
    body = fill_template(
        TEXT, SEL=json.dumps(args.selector), REDACT="true" if args.redact else "false",
    )
    _, value = run_js(args.tab, body)
    emit("text", op_result(value)["text"], raw_text=True)


def cmd_source(args) -> None:
    tab_id, html = run_js(args.tab, "() => document.documentElement.outerHTML")
    path = out_dir() / f"{time.strftime('%Y%m%d-%H%M%S')}-source.html"
    path.write_text(html or "", encoding="utf-8")
    print(f"{tab_id}: {len(html or '')} chars of rendered HTML saved to {path}")


def cmd_click(args) -> None:
    if args.selector is None and args.text is None:
        raise SafariError("click needs a selector, --text, or both")
    body = fill_template(
        CLICK,
        SEL=json.dumps(args.selector or CLICKABLE),
        TEXT=json.dumps(args.text),
        NTH=json.dumps(args.nth),
    )
    tab_id, value = run_js(args.tab, body)
    print(f"{tab_id}: clicked {op_result(value)['clicked']}")


def cmd_fill(args) -> None:
    body = fill_template(FILL, SEL=json.dumps(args.selector), VALUE=json.dumps(args.value))
    tab_id, value = run_js(args.tab, body)
    print(f"{tab_id}: {args.selector} now holds {op_result(value)['filled']} chars")


def cmd_wait(args) -> None:
    if args.selector is not None:
        kind, arg = ("gone" if args.gone else "selector"), args.selector
    elif args.text is not None:
        kind, arg = "text", args.text
    else:
        kind, arg = "load", None
    body = fill_template(WAIT[kind], SEL=json.dumps(arg), TEXT=json.dumps(arg))
    if not poll(args.tab if args.tab else call("info")["tab"], body, args.timeout):
        raise SafariError(f"timed out after {args.timeout:g}s waiting for {kind}" + (f" {arg!r}" if arg else ""))
    print(f"ready: {kind}" + (f" {arg!r}" if arg else ""))


def cmd_copy(args) -> None:
    read_body = (
        as_function(args.js) if args.js is not None
        else fill_template(READ_VALUE, SEL=json.dumps(args.selector))
    )
    fill_body = fill_template(FILL, SEL=json.dumps(args.field), VALUE=PLACEHOLDER)
    reply = call(
        "copy", js=True,
        placeholder=PLACEHOLDER,
        readCode=envelope(read_body),
        fillTemplate=envelope(fill_body),
        expectPrefix=args.expect_prefix,
        **{"from": args.source, "to": args.dest},
    )
    checked = f", starting with {args.expect_prefix!r}" if args.expect_prefix else ""
    print(
        f"copied {reply['length']} chars{checked} from {reply['from']} into {args.field} on {reply['to']}; "
        f"the field now holds {reply['filled']} chars"
    )


def cmd_screenshot(args) -> None:
    path = Path(args.output).expanduser().resolve() if args.output else out_dir() / f"{time.strftime('%Y%m%d-%H%M%S')}-screenshot.png"
    front = call("front", tab=args.tab)
    try:
        time.sleep(RAISE_DELAY)
        proc = subprocess.run(
            ["screencapture", "-x", "-o", f"-l{front['windowId']}", str(path)],
            capture_output=True, text=True, timeout=20,
        )
    finally:
        prev = front.get("prev")
        if prev and prev != "com.apple.Safari":
            try:
                call("activate", bundle=prev)
            except SafariError:
                pass
    if proc.returncode != 0 or not path.exists():
        raise SafariError(
            f"screencapture failed: {proc.stderr.strip() or proc.returncode}. The app running this shell "
            "needs Screen Recording permission, and the Safari window must not be minimized."
        )
    print(f"{front['tab']}: screenshot saved to {path}")


def cmd_close(args) -> None:
    closed = call("close", tab=args.tab)
    print(f"closed {closed['tab']}  {short_url(closed['url'])}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="safari.py", description="Drive the running Safari through Apple Events.")
    sub = root.add_subparsers(dest="cmd", required=True)
    tab = argparse.ArgumentParser(add_help=False)
    tab.add_argument("--tab", help="window:tab id from `tabs`, or a URL/title substring (default: front window's current tab)")

    p = sub.add_parser("tabs", help="list every window's tabs")
    p.add_argument("--full", action="store_true", help="keep query strings and fragments in URLs")
    p.set_defaults(fn=cmd_tabs)

    p = sub.add_parser("navigate", parents=[tab], help="open a URL in a new tab, or in --tab")
    p.add_argument("url")
    p.add_argument("--timeout", type=float, default=20.0)
    p.set_defaults(fn=cmd_navigate)

    p = sub.add_parser("evaluate", parents=[tab], help="run JS and print its JSON result; promises are awaited")
    p.add_argument("code")
    p.add_argument("--timeout", type=float, default=30.0)
    p.set_defaults(fn=cmd_evaluate)

    p = sub.add_parser("text", parents=[tab], help="print the visible text of the page or an element")
    p.add_argument("--selector")
    p.add_argument("--redact", action="store_true", help="mask runs of 24+ token characters")
    p.set_defaults(fn=cmd_text)

    p = sub.add_parser("source", parents=[tab], help="save the rendered HTML to a file")
    p.set_defaults(fn=cmd_source)

    p = sub.add_parser("click", parents=[tab], help="click one element by CSS/XPath and/or visible text")
    p.add_argument("selector", nargs="?")
    p.add_argument("--text", help="match the element's visible text, exact first, then substring")
    p.add_argument("--nth", type=int, help="pick the nth match (1-based) when several match")
    p.set_defaults(fn=cmd_click)

    p = sub.add_parser("fill", parents=[tab], help="set a form field's value the way a framework sees typing")
    p.add_argument("selector")
    p.add_argument("value")
    p.set_defaults(fn=cmd_fill)

    p = sub.add_parser("wait", parents=[tab], help="wait for a selector, text, or page load")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--selector")
    group.add_argument("--text")
    p.add_argument("--gone", action="store_true", help="with --selector, wait until it disappears")
    p.add_argument("--timeout", type=float, default=20.0)
    p.set_defaults(fn=cmd_wait)

    p = sub.add_parser("copy", help="move a value between tabs without printing it")
    p.add_argument("--from", dest="source", required=True, help="tab to read from")
    p.add_argument("--to", dest="dest", required=True, help="tab holding the field")
    p.add_argument("--field", required=True, help="CSS/XPath of the destination field")
    read = p.add_mutually_exclusive_group(required=True)
    read.add_argument("--selector", help="element whose value or text is copied")
    read.add_argument("--js", help="JS returning the value to copy")
    p.add_argument("--expect-prefix", help="refuse unless the value starts with this; nothing of the value is printed")
    p.set_defaults(fn=cmd_copy)

    p = sub.add_parser("screenshot", parents=[tab], help="capture the tab's window (raises Safari for a moment)")
    p.add_argument("--output")
    p.set_defaults(fn=cmd_screenshot)

    p = sub.add_parser("close", help="close one tab")
    p.add_argument("--tab", required=True, help="window:tab id from `tabs`, or a URL/title substring")
    p.set_defaults(fn=cmd_close)
    return root


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        args.fn(args)
    except SafariError as e:
        print(f"use-safari: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
