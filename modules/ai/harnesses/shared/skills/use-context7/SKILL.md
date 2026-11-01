---
name: use-context7
description: Fetches current library and framework docs and code examples from Context7. Use for "check the docs for X" or how a library works. NOT for indexed repos (use-nia) or the library (bilbo:reference).
allowed-tools: Bash(uv run *), Read
argument-hint: "[resolve|query|lookup|raw] [args]"
---

# use-context7 -- on-demand Context7 documentation wrapper

Query up-to-date library and framework documentation from Context7 without
keeping the MCP server registered in agent context permanently. The wrapper
script speaks JSON-RPC 2.0 over HTTP (streamable-http transport) directly to
`https://mcp.context7.com/mcp`, so there is no subprocess to manage.

## When NOT to use this skill

- **Indexed external repos, docs sites, or papers** — use `use-nia`; Context7 only covers published library/framework documentation.
- **General web search or research** — use `/use-bright-data` for scraping/search, or `/research` for orchestrated multi-source research.
- **Codebase-specific questions** — use `grep`/`Read` on the actual repo.
- **Reference notes** - use recall.

## Why this design

Permanently registering the Context7 MCP loads its tool schemas into every
conversation, even conversations that never query library docs. This skill
avoids that context cost: the MCP is only touched when you invoke a subcommand,
and the tool schemas never enter the agent's working context.

## Quick usage

```
SCRIPT={baseDir}/scripts/context7.py
uv run $SCRIPT <subcommand> [args]
```

## Subcommand reference

### resolve -- resolve a library name to its Context7 ID

```bash
uv run $SCRIPT resolve "Next.js"
uv run $SCRIPT resolve "React" --query "server components"
```

Returns the top matches with their Context7 library IDs (e.g. `/vercel/next.js`).
Use the ID in subsequent `query` calls.

`--query` is optional context that helps rank results when the library name is
ambiguous (e.g. "express" could match several packages).

### query -- fetch documentation for a known library ID

```bash
uv run $SCRIPT query "/vercel/next.js" "how do I use server actions?"
uv run $SCRIPT query "/mongodb/docs" "aggregation pipeline examples"
```

The first argument is the Context7 library ID (from `resolve`). The second is
your question. The server returns relevant documentation snippets and code
examples.

**You must resolve the library ID first.** Passing a plain name like "Next.js"
instead of "/vercel/next.js" will fail.

### lookup -- convenience: resolve + query in one step

```bash
uv run $SCRIPT lookup "Next.js" "how do I use server actions?"
uv run $SCRIPT lookup "Prisma" "relation queries"
```

Calls `resolve-library-id` to find the best-matching library, then immediately
calls `query-docs` with that ID. This is the most common usage pattern.

### raw -- escape hatch for any MCP tool

```bash
uv run $SCRIPT raw resolve-library-id --args '{"libraryName":"React","query":"hooks"}'
uv run $SCRIPT raw query-docs --args '{"libraryId":"/facebook/react","query":"useEffect cleanup"}'
```

Passes the tool name and JSON arguments directly to the MCP server. Use this
when you need full control over the request.

## Output handling

- Results up to 4 KB print inline to stdout
- Larger results spill to `~/.cache/context7-cm/<timestamp>-<label>.json`; the
  script prints the file path and the first 1500 characters inline

## Auth

The script reads the API key at use time: it runs the command
`dnix.ai.secrets.readCommand` names (`op-agent read` by default) on the
reference in `settings.secrets.apiKey`, and exits with a clear error if that
fails. No API key is stored on disk or in the skill's source.

## Common mistakes

- **Calling `query` with a library name instead of a library ID** -- use
  `resolve` first to get the ID (e.g. `/vercel/next.js`), or use `lookup` which
  does both steps automatically
- **Omitting the query in `resolve`** -- the query parameter is optional for
  `resolve` but helps the server rank ambiguous results; include it when the
  library name is generic
- **Using this for general web search** -- Context7 only indexes library and
  framework documentation; for general research use `/research` or bright-data

## Dependencies

`uv` must be on PATH (`brew install uv`). The script declares `httpx` as an
inline dependency and `uv run --script` installs it automatically on first run.

The secret reader must be on PATH, for the API key.

## Hard prohibitions

- Do not invent or paraphrase documentation results; if the call fails, report
  the error verbatim so the user gets accurate diagnostic information
- Do not copy the API key out of its vault; never paste it into source,
  logs, or chat output
