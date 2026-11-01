---
name: use-nia
description: Indexes and semantically searches external repos, docs sites and papers through the Nia knowledge agent. Use for indexing a repo or searching Nia. NOT for library docs (use-context7) or web search (use-bright-data).
allowed-tools: Bash(uv run *), Read
argument-hint: "[index|search|manage|read|grep|explore|research|context|advisor|tracer|raw] [args]"
---

# use-nia -- on-demand Nia knowledge agent via nia-mcp-server

Index and search external repositories, documentation, research papers, and
local folders without keeping the MCP registered permanently. The wrapper spawns
`nia-mcp-server` as a short-lived stdio subprocess via `uvx` (version-pinned),
runs one or more tool calls, then terminates it. The main agent context stays
clean.

## When NOT to use this skill

- **Published library/framework documentation** — use `use-context7`; it is faster and purpose-built for that.
- **Reference notes** - use recall.
- **Local codebase search** — use `grep`/`find`/`Read` directly on files already in the working tree.
- **Plain web search with no indexing need** — use `/use-bright-data`.

**Why this design.** Registering the Nia MCP in `~/.claude.json` loads 16 tool
schemas into every conversation -- even when you never touch external code or
docs. This skill loads nothing until you invoke a subcommand, and cleans up
immediately after.

## Nia-first workflow

**Before reaching for web search or fetch, check Nia first.**

1. `manage list` -- see what is already indexed
2. If the source exists, use `search`, `grep`, `read`, `explore` for targeted queries
3. If the source is not indexed but you know the URL, `index <url>` then query
4. Only if no source is known, use `research --mode quick` to discover URLs, then index

Indexed sources give more accurate, complete context than web fetches. WebFetch
returns truncated/summarized content; Nia provides full source code and docs.

## Usage

All subcommands run through one script:

```bash
SCRIPT={baseDir}/scripts/nia.py
uv run $SCRIPT <subcommand> [args]
```

## Subcommand reference

### search -- semantic search across indexed sources

The most common subcommand. Searches all indexed repositories and data sources.

```bash
uv run $SCRIPT search "how does streaming work in vercel ai-sdk"
uv run $SCRIPT search "retry logic" --repos vercel/ai-sdk
uv run $SCRIPT search "authentication" --mode repositories
```

Options: `--repos owner/repo` (comma-separated), `--sources source_id`, `--mode unified/repositories/sources`

### manage -- list, check status, rename, delete, subscribe

```bash
uv run $SCRIPT manage list
uv run $SCRIPT manage list --query "react"
uv run $SCRIPT manage status --id "vercel/ai-sdk"
uv run $SCRIPT manage delete --id "old-source-id"
uv run $SCRIPT manage subscribe --id "vercel/ai-sdk"
```

Actions: `list`, `status`, `rename`, `delete`, `subscribe`. Options: `--query`, `--id`, `--type repo/docs`, `--limit 10`

### index -- index a repo, docs site, or paper

```bash
uv run $SCRIPT index https://github.com/vercel/ai-sdk
uv run $SCRIPT index https://docs.anthropic.com --type docs
uv run $SCRIPT index https://arxiv.org/abs/2301.00001 --type paper
uv run $SCRIPT index https://github.com/vercel/ai-sdk --branch v4
```

Options: `--type repo/docs/paper` (auto-detected from URL), `--branch main`

### grep -- regex search in indexed code

```bash
uv run $SCRIPT grep "useChat" --type repository --repo vercel/ai-sdk
uv run $SCRIPT grep "TODO|FIXME" --repo vercel/ai-sdk --exhaustive
uv run $SCRIPT grep "class.*Error" --repo vercel/ai-sdk --case-sensitive
```

Options: `--type repository`, `--repo owner/repo`, `--exhaustive`, `--case-sensitive`

### explore -- browse file structure

```bash
uv run $SCRIPT explore --type repository --repo vercel/ai-sdk --action tree
uv run $SCRIPT explore src/core --type repository --repo vercel/ai-sdk --action ls
```

Options: `--type repository`, `--repo owner/repo`, `--action tree/ls`

### research -- AI-powered research

```bash
uv run $SCRIPT research "best practices for streaming LLM responses"
uv run $SCRIPT research "compare React Server Components vs Remix" --mode deep
uv run $SCRIPT research "transformer attention mechanisms" --mode oracle --num 10
```

Options: `--mode quick/deep/oracle`, `--num 5`, `--repos owner/repo`, `--sources source_id`

### read -- read file content from indexed sources

```bash
uv run $SCRIPT read vercel/ai-sdk:src/index.ts --type repository
uv run $SCRIPT read vercel/ai-sdk:README.md --type repository --start 1 --end 50
```

Options: `--type repository/docs/package/local_folder`, `--start N`, `--end N`

### context -- cross-agent context sharing

```bash
uv run $SCRIPT context save --title "AI SDK findings" --content "The streaming API uses..."
uv run $SCRIPT context list
uv run $SCRIPT context search --query "streaming"
uv run $SCRIPT context retrieve --id "ctx-123"
```

Actions: `save`, `list`, `retrieve`, `search`, `update`, `delete`. Options: `--query`, `--content "..."`, `--title "..."`, `--id`, `--tags "tag1,tag2"`

### advisor -- analyze code against docs

```bash
uv run $SCRIPT advisor "Is this implementation correct?" --codebase '{"files":{"src/app.ts":"..."}}'
```

Options: `--codebase '{...}'` (JSON: `{files: {path: content}}`), `--format markdown/json`

### tracer -- live GitHub search

```bash
uv run $SCRIPT tracer "streaming implementation" --repo vercel/ai-sdk
uv run $SCRIPT tracer "error handling" --mode search --repos vercel/ai-sdk,langchain-ai/langchainjs
```

Options: `--mode agent/search/list/read/glob`, `--repo owner/repo`, `--repos owner/repo` (comma-separated)

### raw -- escape hatch for all 16 tools

```bash
uv run $SCRIPT raw index --args '{"url":"https://github.com/vercel/ai-sdk","resource_type":"repository"}'
uv run $SCRIPT raw nia_package_search_hybrid --args '{"query":"react state management"}'
uv run $SCRIPT raw auto_subscribe_dependencies --args '{"repository":"vercel/ai-sdk"}'
```

Any Nia MCP tool is reachable via `raw`. Pass the tool name and JSON arguments.

## Output handling

- Short results (<=4 KB text) print to stdout inline.
- Larger results save to `~/.cache/nia-cm/<timestamp>-<label>.json` -- the path is printed along with the first 1500 characters.
- Read saved paths with the `Read` tool to see the full content.

## Auth

The script reads the API key at use time: it runs the command
`dnix.ai.secrets.readCommand` names (`op-agent read` by default) on the
reference in `settings.secrets.apiKey`, and exits with a clear error if that
fails. No API key is stored on disk or in the skill's source.

## Common mistakes

1. **Searching before checking what is indexed.** Always `manage list` first to
   see available sources. Searching unindexed repos returns nothing.
2. **Using `read` without `--type`.** The `--type` flag is required for `read`.
   Common values: `repository`, `docs`, `package`, `local_folder`.
3. **Passing a plain repo name to `grep`/`explore` without `--repo`.** Use
   `--repo owner/repo` (e.g. `--repo vercel/ai-sdk`), not just the repo name.
4. **Using this for local codebase search.** Nia indexes *external* sources. For
   files in the current working tree, use grep/find/read directly.
5. **Skipping Nia in favor of web search.** Indexed sources provide full,
   accurate context. Always check Nia first before falling back to bright-data
   or web fetch.

## Dependencies

- `uv` must be on PATH (for the `uv run --script` shebang and the `uvx` that
  spawns nia-mcp-server). The script finds `uvx` via `shutil.which("uvx")`.
- The secret reader on PATH, for the API key.

## Known limits

- **Startup latency.** The first `uvx nia-mcp-server@<pin>` call installs the
  pinned version into uv's cache (~5-15s); later calls reuse it. Bumping the pin
  (in the script) refreshes it deliberately.
- **Research timeouts.** `research --mode oracle` can take 60-120s. The script
  uses a 180s timeout for tool calls.
- **Indexing is async.** `index` starts indexing but does not wait for
  completion. Use `manage status --id <identifier>` to check progress.
- **Rate limits.** Nia's API has rate limits. Avoid tight loops of search calls.
  Batch your queries where possible.

## Design notes

**No persistent subprocess.** The MCP subprocess starts, handles one request,
and terminates. No state leaks between calls.

**uvx, pinned.** Running `uvx nia-mcp-server@<version>` gives an isolated
install of exactly the pinned version -- no dependency conflicts with other
tools, and no floating to whatever is newest on PyPI at call time.

**180s tool timeout.** Research and indexing operations can be slow. The default
60s timeout from other skills would cause false timeouts here. The 60s startup
timeout accounts for uvx needing to install the package on a cold cache.
