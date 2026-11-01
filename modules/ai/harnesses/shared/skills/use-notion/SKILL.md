---
name: use-notion
description: Reads and writes Notion pages, databases and comments across several workspaces. Use for a Notion page or URL, searching a workspace, querying a database, drafting a page. NOT for the library (bilbo:reference) or Google Docs (use-google-workspace).
allowed-tools: Bash(uv run *), Read
argument-hint: "[accounts|search|read|db|query|create|update|comment|raw] [args]"
---

# use-notion — Notion across several workspaces, on demand

Read and write Notion without registering its MCP server permanently. The
wrapper spawns `@notionhq/notion-mcp-server` as a short-lived stdio subprocess,
runs the call, and kills it — 24 tool schemas stay out of the agent's context,
and `NOTION_TOKEN` is picked per `--account` so each call hits exactly one
workspace.

## When NOT to use this skill

- **PRDs, specs, standards, design docs** - those live as sources in bilbo's library (`bilbo:reference`), not Notion.
- **bilbo's notes** - use `bilbo:recall`; they are not in Notion.
- **Google Docs, Drive, Sheets** — use `/use-google-workspace`.
- **Reading a public Notion page with no auth** — `WebFetch` is faster and needs no integration.

## Why this design

Registering the Notion MCP in `~/.claude.json` injects 24 tool schemas into every
conversation, even ones that never touch Notion. This skill loads nothing until a
subcommand runs. The local server is also the only Notion transport that takes a
plain integration token: the hosted server at `mcp.notion.com` is OAuth-only with
~8h tokens, which makes several workspaces mean several browser flows and breaks
outright in any non-interactive run. One token per workspace, selected by a flag,
is what makes multi-account cheap here.

The trade is that the local server's search is **title-match only** — the hosted
server's semantic search across the workspace and connected apps (Slack, Drive,
Jira) is not available. When a title search comes up empty, fall back to `query`
against a known database, or ask the user for the page URL.

## Transports

Each account in the skill's settings declares how it is reached. Subcommands are the
same either way; the transport is a property of the profile, not of the command.

| `transport` | Auth | Covers | Use when |
|---|---|---|---|
| `local` (default) | integration token | everything, read + write | you can create an integration and connect it |
| `browser` | your logged-in Chrome session | `search`, `read` only | Notion permits no token for your role |
| `auto` | local, falling back to browser | per whichever answers | a profile that may have a token later |

**Why a second transport exists.** Notion gates its integration platform by role
and by an admin allowlist: a guest, or a member without an allowlist entry, cannot
create an integration *or* install the MCP connector, so there is no token to
obtain for that workspace. The `browser` transport reaches it the way `use-slack`
reaches Enterprise Grid — by running the request inside a page you are already
signed in to, over CDP. Nothing is extracted or stored: `fetch` runs in an
`app.notion.com` tab with `credentials: 'include'`, so the session cookies ride
along and the call originates from Notion's own origin.

Its costs, and why it is never the default: it speaks Notion's private `/api/v3`,
which is undocumented and can change shape without notice; it is read-only; and it
needs Chrome alive on the debug port. Prefer `local` wherever a token is available.

**Browser transport prerequisites.** `chrome_up` (or any Chrome on
`--remote-debugging-port=9222`), signed in to Notion in that profile. If the
session lapses, calls fail with a 401 naming the fix.

**Guests get roots, not a workspace.** On the browser transport a guest's
`getSpaces` returns the shared root pages rather than the whole workspace, so
`search` walks out from those roots. A page nobody shared with you is invisible —
that is the account's own permissions, unchanged by the transport.

## Usage

```bash
SCRIPT={baseDir}/scripts/notion.py
uv run $SCRIPT <subcommand> [args]
```

**Always invoke via `uv run`** — it installs the inline PEP 723 dependencies; a
bare `python3` call fails.

Every subcommand accepts `--account <name>`, which also selects the transport. Without it the account marked
`default = true` in the settings wins (or `NOTION_ACCOUNT`, or the lone
configured account). Any subcommand accepts `--json` to get the raw API payload
instead of the digest.

Page arguments accept a **Notion URL, a bare 32-hex id, or a dashed UUID** —
paste the URL from the browser and the script extracts the id.

## Reading

### accounts — what workspaces are reachable

```bash
uv run $SCRIPT accounts
uv run $SCRIPT accounts --no-verify
```

Lists each configured account, where its token comes from, and (by default) calls
the API once per account to confirm the token works and print the workspace name.
Run this first when the user names a workspace you have not used this session, or
when anything returns an auth error.

### search — find a page by title

Title match on both transports (`local` asks Notion's search endpoint; `browser`
walks out from the shared roots), so an empty result never proves absence.

```bash
uv run $SCRIPT search "Q3 roadmap"
uv run $SCRIPT search "retro" --type page --limit 10
uv run $SCRIPT search --type data_source          # list every database shared with the integration
```

Title match only, over pages and data sources the integration has been connected
to. An empty result usually means the integration lacks access, not that the page
is missing — see Gotchas.

### read — a page's content as Markdown

```bash
uv run $SCRIPT read https://www.notion.so/Some-Page-abc123...
uv run $SCRIPT read abc123... --transcript
```

Returns Notion-flavored Markdown, which is far cheaper in tokens than block JSON
and is the same text `update --edit` matches against. `--transcript` expands
meeting-note transcripts, which are otherwise a placeholder link.

### db and query — databases

```bash
uv run $SCRIPT db https://www.notion.so/workspace/abc123...     # -> data source ids
uv run $SCRIPT query <data-source-id> --limit 20
uv run $SCRIPT query <data-source-id> --filter '{"property":"Status","status":{"equals":"In progress"}}'
uv run $SCRIPT query <data-source-id> --sorts '@sorts.json'
```

**A database id will not work on `query`.** Since API version 2025-09-03 a
database is a container and its rows live on a *data source*; `db` exists to hand
you those ids. Both `--filter` and `--sorts` take inline JSON or `@file.json`.

For filter and sort shapes, read `references/queries.md`.

### props, comments, users

```bash
uv run $SCRIPT props <page>        # property values as JSON (not page content)
uv run $SCRIPT comments <page>
uv run $SCRIPT users
```

## Writing

Every write requires `--yes`. Without it the script prints exactly what it would
have done and exits — run it bare first, show the user that line, and only re-run
with `--yes` after they confirm.

### create — a new page

```bash
uv run $SCRIPT create --parent <page-url> --title "Q3 retro" --md-file draft.md --yes
uv run $SCRIPT create --parent <db-url> --in-database --title "Fix login" \
  --properties '@props.json' --yes
```

Creates the page, then writes the body as Markdown in a second call (the create
API takes block JSON, not Markdown, so the script splits it). Under a database,
pass `--in-database`; if the title property is not literally named `title`, pass
`--title-property "<Name>"`.

### update — edit page content

```bash
# surgical: find-and-replace, repeatable, this is the default and safest mode
uv run $SCRIPT update <page> --edit "Status: draft" "Status: shipped" --yes
uv run $SCRIPT update <page> --edit "old" "new" --edit "foo" "bar" --all --yes

# destructive: replace the entire page body
uv run $SCRIPT update <page> --md-file rewrite.md --yes
```

`--edit` matches the Markdown exactly as `read` returned it, so **`read` the page
first** and copy the string. Prefer `--edit` over `--md-file`: a full overwrite
discards anything not in the new text. Child pages and databases dropped by an
edit are protected unless `--allow-deleting` is also passed.

### set-props, comment, move, archive

```bash
uv run $SCRIPT set-props <page> --properties '{"Status":{"status":{"name":"Done"}}}' --yes
uv run $SCRIPT comment <page> "Reviewed, one nit in the schema section" --yes
uv run $SCRIPT move <page> --to <parent-page> --yes
uv run $SCRIPT archive <page> --yes           # to trash
uv run $SCRIPT archive <page> --restore --yes
```

`archive` moves a page to the trash where the user can restore it from the UI;
there is no hard-delete in this skill.

## Escape hatches

```bash
uv run $SCRIPT tools                       # live tool list from the pinned server
uv run $SCRIPT raw API-retrieve-a-block --args '{"block_id":"abc123..."}'
uv run $SCRIPT raw API-update-a-block --args '@block.json' --yes
```

`raw` reaches any of the 24 tools, and refuses write tools without `--yes`. The
tool names are 1:1 with the REST API (`API-post-search`, `API-post-page`, …) and
are **not** the names in Notion's public MCP docs, which describe the different,
hosted server. Read `references/tools.md` before composing a `raw` call.

## Working across accounts

There is no cross-workspace API. Moving content between workspaces is two
explicit calls, and the agent must say which account each one hits:

```bash
uv run $SCRIPT --account main read <page> > /tmp/page.md
uv run $SCRIPT --account team create --parent <dest> --title "Copied" \
  --md-file /tmp/page.md --yes
```

Never assume the default account when the user names a workspace. If the account
name they use is not configured, run `accounts` and ask which one they
mean rather than guessing.

## Configuration

Accounts come from `dnix.ai.skills.use-notion.settings`. A Notion integration
token belongs to exactly one workspace, so an account is one workspace:

- `secrets.<name>` is the reference to that account's token. Every name here is
  an account; the default is `main`, at `op://<vault>/Notion/credential`.
- `accounts.<name>` takes `default = true` (on one account) and `transport`. A
  browser account has an entry here and no secret.

Each token is read at use time: the script runs the command
`dnix.ai.secrets.readCommand` names (`op-agent read` by default) on the
reference, so it never touches disk.

Creating one, per workspace: <https://www.notion.so/profile/integrations> → New
integration → scope it to that workspace → store the `ntn_` secret where the
reader finds it.

## Gotchas

- **An integration sees only what it is connected to.** A new integration sees an
  empty workspace until someone opens a page or teamspace and adds it under
  Connections. This is the cause of nearly every "page not found" and every empty
  `search`. Tell the user to connect the page rather than retrying the call.
- **Database id vs data source id** — the 2025-09-03 split, above. Any recipe
  using `POST /v1/databases/:id/query` is stale.
- **Search is title-only.** No body text, no semantic match. Do not report "there
  is nothing about X in Notion" on the strength of an empty `search`.
- **~3 requests/sec per integration.** The script throttles itself; batch related
  questions into one `query` rather than looping page-by-page.
- **`page_size` caps at 100** on every paginated tool; the script follows
  `next_cursor` up to `--limit`.
- **Output over 4 KB spills** to `~/.cache/notion-cm/` and prints the path plus
  the first 1500 characters. Read the file if the rest matters.
- **`search` and `read` are the whole browser transport.** `db`, `query`, `props`,
  `comments`, `users` and every write need `transport = "local"`; on a browser
  profile they exit with that message rather than failing obscurely.
- **A browser profile needs no token at all.** Its settings entry is just
  `accounts.<name>.transport = "browser"`.
- **Notion may sunset the local server** in favor of the hosted one. If the pinned
  version stops working, the fallback is the hosted OAuth server — a transport
  change inside `notion.py`, not a rewrite of this skill.

## Dependencies

`uv` on PATH (`brew install uv`) and `npx` (Node, via Volta). The MCP package is
pinned to `@notionhq/notion-mcp-server@2.5.1` in `scripts/notion.py`. The secret
reader must be on PATH for a `local` account.

## Hard prohibitions

- Never run a write subcommand with `--yes` before the user has seen and approved
  what it will do. Run it bare, show them the refusal line, then re-run.
- Never pass `--allow-deleting` unless the user explicitly asked to remove the
  child pages it would drop; it destroys subtrees that no `--edit` would touch.
- Never overwrite a page with `--md-file` when a targeted `--edit` would do.
- Never guess which account a request means. Resolve it with `accounts` or ask.
- Never copy tool names from Notion's MCP documentation into `raw`; that page
  documents the hosted server. Use `tools` or `references/tools.md`.
- Never use the browser transport for a workspace where a `local` token is
  available; it is the fallback for workspaces that permit no token, not a way
  around configuring one.
- Never paste an `ntn_` token into source, logs, chat, or a commit. It lives in
  the secret store, nowhere else.
- Never report Notion content you did not read in this session. If a call fails,
  surface the error verbatim.
