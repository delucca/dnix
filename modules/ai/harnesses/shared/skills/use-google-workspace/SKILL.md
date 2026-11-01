---
name: use-google-workspace
description: Reads and writes Google Docs, Drive files and Sheets on the personal account. Use for editing a doc, searching Drive, a Sheet link. NOT for the work account or non-Google files.
allowed-tools: Bash(uv run *), Read
argument-hint: "[auth|tools|doc-get|doc-md|doc-create|doc-inspect|doc-modify|doc-find-replace|drive-search|drive-list|drive-get|drive-create|drive-link|sheet-read|sheet-write|sheet-create|sheet-info|raw] [args]"
---

# use-google-workspace -- on-demand Google Docs/Drive/Sheets via workspace-mcp

Read and edit Google Docs, Drive files, and Sheets on the **personal** Google
account without permanently registering an MCP. The wrapper spawns
`workspace-mcp` (taylorwilsdon/google_workspace_mcp) as a short-lived stdio
subprocess via `uvx`, performs one tool call, then terminates it. The main agent
context stays clean.

## When NOT to use this skill

- **Reference notes** - use recall.
- **Local files** — use the built-in `Read`/`Write`/`Edit` tools.
- **A work Google account** — this skill authenticates with personal OAuth credentials; work docs need the work account's own tooling.
- **Non-Google documents** — anything not a Docs/Sheets/Drive file is out of scope.

**Why this design.** Registering a Google Workspace MCP loads ~50 tool schemas
into every conversation, even when you never touch a doc. This skill loads
nothing until you invoke a subcommand, and tears the subprocess down right
after. The OAuth client credentials stay out of `~/.claude.json`, out of git and
off disk: the script reads them at use time through the command
`dnix.ai.secrets.readCommand` names (`op-agent read` by default), which never
prompts, so background and agent runs work unattended.

**Why workspace-mcp and not the Drive REST API or Google's official MCP.**
Google's official Workspace MCP ships no Docs *editing* server (Drive MCP is
file-level only) and is OAuth-only. workspace-mcp is the cleanest off-the-shelf
server that exposes real surgical Docs edits (`modify_doc_text`,
`find_and_replace_doc`, `batch_update_doc`) plus `inspect_doc_structure`, which
computes the safe insertion indexes so the LLM never has to count characters.

## Usage

All subcommands run through one script:

```bash
SCRIPT={baseDir}/scripts/google_workspace.py
uv run "$SCRIPT" <subcommand> [args]
```

Run `uv run "$SCRIPT" auth` **once per machine** before anything else.

## One-time setup (per Google Cloud project)

Do this once. It is not automated because it requires the Google Cloud console.

1. **Create / pick a Google Cloud project**, then enable these APIs:
   Google **Docs API**, **Drive API**, **Sheets API**.
2. **OAuth consent screen**: User type *External*, publishing status *Testing*,
   and add your own Google address under *Test users* (so consent works without
   app verification).
3. **Create an OAuth client** of type **Desktop app**. Note the client ID (and
   secret -- a Desktop client's secret is not really secret, but store it
   anyway).
4. **Store the credentials where the secret reader finds them**: by default
   the item `Google Workspace` in the op-agent vault, with three fields:
   - `client_id`
   - `client_secret`
   - `email` -- the Google address the docs live under

   `settings.secrets.clientId`, `clientSecret` and `email` hold the three
   references; override them for another item.
5. **Authenticate**: `uv run "$SCRIPT" auth`
   - On the **laptop**: a browser opens, you grant access, done.
   - On the **debian server** (headless): first open an SSH tunnel so the
     OAuth callback reaches a real browser:
     `ssh -L 8000:localhost:8000 <server>`, run `auth` on the server, then run
     the `open "$(ssh <host> cat ...)"` command `auth` prints.
   - The refresh token is cached under `~/.google_workspace_mcp/credentials`;
     every later call runs headless. Tokens are machine-bound -- run `auth` on
     each machine rather than copying the directory.

**Never copy the authorization URL out of a terminal.** It is ~700 characters,
the terminal wraps it, and the copied line breaks arrive as spaces inside the
`scope` parameter -- Google splits two scopes into four fragments and fails the
flow with `Error 400: invalid_scope` (`invalid=[ht, https://w, ...]` in the
message is the tell). `auth` therefore stages the URL to
`~/.google_workspace_mcp/credentials/auth_url.txt` and prints a short command
that opens it from there; run that, don't reconstruct the URL by hand.

If a command later fails with an auth/credential error, just run `auth` again.

## The index-safe editing workflow (read this before editing)

Google Docs positions are **UTF-16 code-unit offsets, scoped per segment**
(body, header, footer, footnote, tab). Every insert/delete shifts all higher
indexes, and emoji/surrogate-pair characters count as two. Never guess an index.

For any edit that targets a position:

1. `doc-inspect <id>` first -- it returns safe insertion points, element
   start/end indexes, segment IDs, named ranges, and the max safe index.
2. Plan edits from that structure. Prefer **`doc-find-replace`** (anchor by
   text, no index math) whenever you can describe the change as "replace X
   with Y".
3. Use **`doc-modify`** only with indexes you read from `doc-inspect`. When
   issuing several positional edits, apply them **highest index first** so
   earlier edits don't invalidate later offsets.
4. Re-`doc-inspect` after structural changes before the next positional edit.

This avoids the classic agent failure mode of deleting and rewriting the whole
document, which destroys version history, comments, and attribution.

## Subcommand reference

### Docs

```bash
uv run "$SCRIPT" doc-get <document_id>            # plain text content
uv run "$SCRIPT" doc-md  <document_id>            # markdown (+comments)
uv run "$SCRIPT" doc-md  <document_id> --no-comments
uv run "$SCRIPT" doc-create "Q3 Plan" --content "First line"
uv run "$SCRIPT" doc-inspect <document_id>        # safe indexes / structure
uv run "$SCRIPT" doc-inspect <document_id> --detailed --tab <tab_id>
uv run "$SCRIPT" doc-find-replace <document_id> --find "TBD" --replace "2026-Q3"
uv run "$SCRIPT" doc-modify <document_id> --start 25 --text "inserted text"
uv run "$SCRIPT" doc-modify <document_id> --start 10 --end 18 --bold --text "Heading"
```

`doc-modify` options: `--start` (required, UTF-16 index), `--end`, `--text`,
`--segment-id`, `--tab`, `--bold`, `--italic`, `--underline`, `--font-size`,
`--font-family`, `--text-color` (hex), `--link-url`.

### Drive

```bash
uv run "$SCRIPT" drive-search "name contains 'budget'"
uv run "$SCRIPT" drive-search "mimeType='application/vnd.google-apps.document'" --limit 20 --order-by "modifiedTime desc"
uv run "$SCRIPT" drive-list                       # root folder
uv run "$SCRIPT" drive-list <folder_id> --type document
uv run "$SCRIPT" drive-get <file_id>              # file content
uv run "$SCRIPT" drive-create notes.txt --content "hello"
uv run "$SCRIPT" drive-link <file_id>             # shareable link
```

`drive-search` uses Google Drive query syntax. To find a doc's ID from a name,
search first, then pass the returned ID to the doc commands.

### Sheets

```bash
uv run "$SCRIPT" sheet-read <spreadsheet_id>                 # A1:Z1000
uv run "$SCRIPT" sheet-read <spreadsheet_id> "Sheet1!A1:D50" --formulas
uv run "$SCRIPT" sheet-write <spreadsheet_id> "Sheet1!A1:B2" --values '[["a",1],["b",2]]'
uv run "$SCRIPT" sheet-write <spreadsheet_id> "Sheet1!A1:B2" --clear
uv run "$SCRIPT" sheet-create "Tracker" --sheets "Jan,Feb,Mar"
uv run "$SCRIPT" sheet-info <spreadsheet_id>
```

`sheet-write --values` takes a JSON list-of-lists. Default input mode is
`USER_ENTERED` (formulas/dates parsed); pass `--raw` to store values verbatim.

### Discovery and escape hatch

```bash
uv run "$SCRIPT" tools                 # list every tool the server exposes
uv run "$SCRIPT" tools --schema        # include full input schemas
uv run "$SCRIPT" raw <tool> --args '{"document_id":"...", ...}'
```

`raw` reaches any workspace-mcp tool not wrapped above (e.g. `insert_doc_image`,
`update_paragraph_style`, `batch_update_doc`, `manage_drive_access`,
`append_table_rows`). Use `tools --schema` to read the exact argument names
first. `user_google_email` is injected automatically for every call.

## Write safety

Editing or creating content is a real, externally-visible side effect on the
user's Google account.

- Only run the **write** subcommands (`doc-create`, `doc-modify`,
  `doc-find-replace`, `drive-create`, `sheet-write`, `sheet-create`, and any
  `raw` write tool) when the user has explicitly asked for that change.
- Before a write, state exactly which document/range you will change and what
  the new content is. For find/replace, show the find and replace strings.
- Reads (`doc-get`, `doc-md`, `doc-inspect`, `drive-search`, `drive-list`,
  `drive-get`, `drive-link`, `sheet-read`, `sheet-info`, `tools`) are safe to
  run as needed.

## Output handling

- Short results (<=4 KB) print inline.
- Larger results (full doc bodies, big ranges) save to
  `~/.cache/google-workspace-cm/<timestamp>-<label>.txt`; the path prints with the
  first 1500 characters. Read saved paths with the `Read` tool.

## Dependencies

- `uv` / `uvx` on PATH (`brew install uv`, or the astral install script on
  debian). The script's shebang uses `uv run --script`; the MCP runs via `uvx`.
- The secret reader on PATH: the credentials are read per call.
- Network access for `uvx` to fetch `workspace-mcp` on first run.

## Known limits

- **First-call latency.** The first `uvx` invocation installs `workspace-mcp`
  and its deps (~20-60s). Subsequent calls reuse the cached, version-pinned
  environment and start in a few seconds.
- **Pinned version.** `WORKSPACE_MCP_VERSION` is pinned in the script (no
  floating versions). Bump it there deliberately and re-test `auth`.
- **Personal account only.** This skill targets the personal Google account.
  It uses OAuth single-user mode -- not service accounts / domain-wide
  delegation (a personal account can't do DWD anyway).
- **Consent expires roughly weekly.** The OAuth consent screen's publishing
  status is *Testing*, and Google expires refresh tokens issued by a Testing
  app after ~7 days. Every call then fails with `invalid_grant: Bad Request`
  until someone re-runs `auth` at the browser. Consent state is per machine.
- **No cross-call atomicity.** Each tool call is independent. For multi-step
  edits, inspect between steps; the document may change under you if a
  collaborator is editing.

## Hard prohibitions

- Never run a write subcommand without an explicit user request and a stated
  preview -- writes are immediately visible, hard-to-undo edits on the user's
  real documents.
- Never pass a Docs index you did not get from `doc-inspect` -- indexes are
  UTF-16 per-segment offsets that shift on every edit, so a guessed one
  corrupts the wrong span.
- Never put the OAuth client ID/secret in source, settings, or this repo. They
  live in the secret store; settings hold only references to them.
- Never use this skill for a work Google account -- it authenticates with
  personal OAuth credentials.
