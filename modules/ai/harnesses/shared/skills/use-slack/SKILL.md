---
name: use-slack
description: Reads, searches and posts to Slack across every workspace on Slack desktop, even Enterprise Grid. Use for reading a channel or sending a message. NOT for bulk inbox triage.
allowed-tools: Bash(uv run *), Read
argument-hint: "[read|thread|search|find-channel|find-user|list-dms|send|raw|discover] [args]"
---

# use-slack — personal Slack over CDP

Talk to Slack from a personal machine: read channels and threads, search,
look up channels, users and DMs, and (with confirmation) post messages — across
**every** workspace you are signed into on the Slack desktop app.

**Why this transport.** Slack's public API returns `enterprise_is_restricted`
on locked-down Enterprise Grid workspaces. The only path that works is to
route calls through Slack's own Electron renderer via Chrome DevTools Protocol:
the request originates from a Slack-signed `app.slack.com` page, which the
policy filter allows, while the per-call `token` scopes it to the right
workspace. Auth (one `xoxc` token per workspace + the shared `d` cookie) is
extracted live from Slack desktop's local state on every run — no bot tokens,
no app install, nothing to manage.

This skill **owns** that transport.

## Requirements

- macOS with **Slack desktop installed**. Slack 4.53+ refuses
  `--remote-debugging-port` on its default profile, so the script runs its own
  Slack instance on the dedicated profile `~/.slack-debug-profile`
  (`SLACK_PROFILE` in `scripts/slack.py`) with `--remote-debugging-port=9229`.
  It launches that instance on demand, reuses it while it runs, and never quits
  or touches your everyday Slack, which keeps running beside it.
- **One-time sign-in.** The first command (any but `discover`) opens the debug
  Slack window and fails with `slack_debug_profile_not_signed_in`. Sign in to
  every workspace you want in that window, then retry. The profile keeps the
  session from then on.
- First run prompts once for Keychain access to "Slack Safe Storage" — click
  **Always Allow** so non-interactive runs don't block.
- `uv` on PATH — every command runs via `uv run`, which installs the script's
  inline dependencies on first use.

**Security note — the CDP debug port stays open.** Once the script launches
the debug Slack with `--remote-debugging-port=9229`, that port keeps listening
on `127.0.0.1` until you quit that instance. Any local process can then drive the Slack
renderer over CDP — read the xoxc token and `d` cookie, send messages in every
signed-in workspace — with no further prompt. The launch no longer passes
`--remote-allow-origins=*`, so browser pages can't reach the port (Chromium's
Origin check blocks them; the Python client sends no Origin header and connects
fine), but local processes are still trusted. The skill does not auto-tear-down
the port; **`Cmd+Q` in the debug Slack window closes it**, and the next skill
run launches the debug instance again.

Verify setup any time with `discover` (no CDP needed; it reads the debug
profile, so it only works after the sign-in):

```bash
SCRIPT={baseDir}/scripts/slack.py
uv run $SCRIPT discover
```

## Usage

All subcommands run through one script. **Always invoke via `uv run`** — it
installs the inline PEP 723 dependencies; a bare `python3` call fails with
`ModuleNotFoundError`.

```bash
SCRIPT={baseDir}/scripts/slack.py
uv run $SCRIPT <subcommand> [args]
```

Operations span every signed-in workspace by default. Scope to one with
`--workspace <domain-or-name>` (e.g. `--workspace acme`). For id-based
commands (`thread`, `raw`) with multiple workspaces, `--workspace` is required
unless the workspace is unambiguous (a permalink encodes it for you).

### read — recent messages in a channel or DM

```bash
uv run $SCRIPT read '#general' --limit 30
uv run $SCRIPT read C012345 --workspace acme
uv run $SCRIPT read general --oldest 1700000000.000000
```

`channel` accepts `#name`, `name`, or a `Cxxxx`/`Dxxxx`/`Gxxxx` id. Names
resolve against the conversations you belong to. Messages print oldest → newest
with timestamps and permalinks.

### thread — a single thread

Easiest: paste the Slack permalink — it encodes the workspace, channel, and
thread root, so no `--workspace` is needed.

```bash
uv run $SCRIPT thread --url 'https://acme.slack.com/archives/C012345/p1700000000123456?thread_ts=1700000000.123456&cid=C012345'
```

Or explicit:

```bash
uv run $SCRIPT thread --channel C012345 --ts 1700000000.123456 --workspace acme
```

### search — messages by query

```bash
uv run $SCRIPT search 'from:@alex in:#payments timeout'
uv run $SCRIPT search 'launch checklist' --workspace acme --limit 30
```

Searches all workspaces by default. Slack operators that work: `from:@user`,
`in:#channel`, `before:YYYY-MM-DD`, `after:YYYY-MM-DD`, `has:link`, quoted
phrases. Returns newest-first; default limit 20 per workspace. This skill has
no bulk mode.

### find-channel — locate a channel by name

```bash
uv run $SCRIPT find-channel oncall
uv run $SCRIPT find-channel payments --workspace acme
```

Lists matching channels (id, name, workspace, public/private). **Only sees
channels you belong to** — it reads your membership, not the full directory.
For a channel you are not in, search its messages instead.

### find-user — look up a user

```bash
uv run $SCRIPT find-user someone@example.com    # exact email — reliable
uv run $SCRIPT find-user "alex"                 # name fragment — best-effort
```

Email does an exact `users.lookupByEmail`. A name fragment scans a capped slice
of the member list, so on large orgs it can miss people — prefer email when you
know it.

### list-dms — your DMs and group DMs

```bash
uv run $SCRIPT list-dms --limit 30
uv run $SCRIPT list-dms --workspace acme
```

### send — post a message (REQUIRES CONFIRMATION)

`send` is the only subcommand that mutates Slack. Before invoking it you MUST:

1. Show the user the **exact** message text.
2. Show the **destination** (resolved `#channel`/DM and any `--thread-ts`).
3. Get explicit approval ("Send this?").

Preview the resolved destination without sending using `--dry-run`:

```bash
uv run $SCRIPT send '#status' 'Rolled out the fix; metrics back to baseline.' --dry-run
```

Only after the human approves, send with `--yes`:

```bash
uv run $SCRIPT send '#status' 'Rolled out the fix; metrics back to baseline.' --yes
uv run $SCRIPT send C012345 'replying in thread' --thread-ts 1700000000.123456 --yes
```

`--yes` is mandatory for the actual send (it does nothing in a non-TTY without
it). Never pass `--yes` without the human confirmation above.

### raw — any Slack method

```bash
uv run $SCRIPT raw conversations.info --args '{"channel":"C012345"}' --workspace acme
uv run $SCRIPT raw reactions.get --args '{"channel":"C012345","timestamp":"1700000000.123456"}'
```

Escape hatch for endpoints the subcommands don't wrap. `raw` posts to
`/api/<method>` with your JSON params plus the workspace token.

## Output handling

- Short results (≤ 4 KB) print inline.
- Larger results spill to `~/.cache/slack-cm/<timestamp>-<op>.txt`; the script
  prints a preview plus the file path. Use the `Read` tool to see the rest.

## Troubleshooting

A failing command prints a one-line reason on stderr. The common ones:

- `slack_app_not_installed` / `slack_desktop_not_installed` — install Slack and
  sign in, then retry.
- `keychain_read_failed` — macOS denied Keychain access; run any command from a
  terminal once and click **Always Allow** on the "Slack Safe Storage" prompt.
- `slack_debug_profile_not_signed_in` — the debug profile has no workspace.
  Sign in in the debug Slack window the run opened (run any command but
  `discover` to open it), then retry.
- `slack_debug_launch_exited` — the debug instance quit right after launch; the
  reason is Slack's last log line, and the full output is in
  `~/.slack-debug-profile/debug-launch.log`. `Refusing to launch:
  --remote-debugging-port requires --user-data-dir pointing outside the default
  profile` means something launched Slack on the default profile with the
  debug port, which Slack 4.53+ refuses.
- `slack_cdp_not_ready_within_timeout` / `cdp_unreachable` — the debug Slack
  did not show a workspace page within 60 s; retry. If it persists, quit the
  debug window and retry so it launches fresh.
- `no_workspaces_in_root_state` — the debug profile lists no workspace; sign in
  again in the debug window.

Start with `discover` (no CDP needed) to confirm auth and workspace detection
before debugging a read/send call.

## Common mistakes

- **Pasting a permalink into `read`.** That's `thread --url`. `read` takes a
  channel.
- **Sending without showing the user first.** Auto-send is the fastest way to
  post to the wrong place. Always confirm, then `--yes`.
- **Expecting `find-channel` to find any channel.** It only sees channels you
  are a member of. Use `search` for messages in channels you have not joined.
- **Bare `python3 slack.py`.** Skips the dependency install. Always `uv run`.
- **Quitting your everyday Slack to fix a CDP error.** The transport only uses
  the debug instance; the everyday one is irrelevant to it.
- **Omitting `--workspace` for an id-based `thread`/`send` with several
  workspaces.** The script asks for it when the target is ambiguous.

## When NOT to use this skill

- **Bulk unread triage across all workspaces** (daily inbox sweep with
  watermarks, threading, classification) → not this skill; the dedicated inbox
  triage pipeline owns that.
- **Non-Slack messaging** (WhatsApp, email) → their own channels/skills.

## Hard prohibitions

- Never `send` (or `raw` a write method like `chat.postMessage`,
  `reactions.add`, `conversations.invite`) without showing the user the exact
  text and destination and getting explicit approval first.
- Never pass `--yes` on the user's behalf — it represents their confirmation.
- Never add bot tokens, install a Slack app, or register an MCP. The transport
  is xoxc + d via Slack desktop only.
