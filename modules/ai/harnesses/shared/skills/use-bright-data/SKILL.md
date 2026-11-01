---
name: use-bright-data
description: Scrapes webpages and runs search queries through Bright Data's proxy network, unlocking bot-protected pages. Use for scraping a page, web search, "google this". NOT for library docs (use-context7) or indexed repos (use-nia).
allowed-tools: Bash(uv run *), Read
argument-hint: "[scrape|batch-scrape|search|batch-search|discover|raw] [args]"
---

# use-bright-data -- on-demand web scraping and search via Bright Data MCP

Scrape web pages and run search engine queries through Bright Data's proxy network without keeping the MCP server registered permanently. The wrapper spawns `@brightdata/mcp` as a short-lived stdio subprocess, runs one tool call, then terminates it. The main agent context stays clean.

## When NOT to use this skill

- **Library or framework documentation** — use `use-context7`; it is faster and purpose-built for that.
- **Indexed repos, docs sites, or papers already in Nia** — use `use-nia` for full-source search instead of a fresh scrape.
- **Reference notes** - use recall.
- **Orchestrated multi-source research** — use `/research`, which fans out across these sources for you.
- **Simple, unprotected URL fetching** — use `WebFetch`; reserve this skill for CAPTCHA/bot-protected pages.

**Why this design.** Registering `@brightdata/mcp` in `~/.claude.json` injects its tool schemas into every conversation -- even when you never scrape anything. This skill loads nothing until you invoke it, and cleans up immediately after.

**Auth.** The script reads the API token at use time: it runs the command `dnix.ai.secrets.readCommand` names (`op-agent read` by default) on the reference in `settings.secrets.apiToken`. Only the API token is needed; the per-zone passwords authenticate the direct superproxy route, which this skill never uses.

## Usage

All subcommands run through one script:

```bash
SCRIPT={baseDir}/scripts/bright-data.py
uv run $SCRIPT <subcommand> [args]
```

### scrape -- Scrape a single URL as markdown

```bash
uv run $SCRIPT scrape https://example.com
uv run $SCRIPT scrape https://news.ycombinator.com/item?id=12345
```

Returns the page content as markdown. Can unlock CAPTCHA and bot-protected pages that `WebFetch` and `curl` would fail on.

### batch-scrape -- Scrape multiple URLs (max 5)

```bash
uv run $SCRIPT batch-scrape https://example.com https://example.org
uv run $SCRIPT batch-scrape https://a.com https://b.com https://c.com
```

Scrapes up to 5 URLs in a single call. Results are printed sequentially, separated by headers.

### search -- Search engine query

```bash
uv run $SCRIPT search "python asyncio tutorial"
uv run $SCRIPT search "site:github.com bright data mcp" --engine google
uv run $SCRIPT search "rust memory safety" --engine bing --geo us
```

Options:
- `--engine` -- google (default), bing, or yandex
- `--geo` -- 2-letter country code for geo-targeted results

### batch-search -- Multiple search queries at once (max 5)

```bash
uv run $SCRIPT batch-search "query one" "query two" "query three"
```

Runs up to 5 search queries simultaneously. Each query uses Google by default. Options apply to all queries:
- `--engine` -- google (default), bing, or yandex
- `--geo` -- 2-letter country code

### discover -- AI-ranked web search

```bash
uv run $SCRIPT discover "best rust web frameworks 2025"
uv run $SCRIPT discover "CAPTCHA bypass techniques" --intent "find open-source libraries"
uv run $SCRIPT discover "climate change data" --num 20 --country us
```

Options:
- `--intent` -- Goal of the search, used for AI relevance ranking
- `--num` -- Number of results to return
- `--country` -- 2-letter ISO country code
- `--language` -- Language filter
- `--start-date` / `--end-date` -- Date range (YYYY-MM-DD)

### raw -- Escape hatch for any Bright Data MCP tool

```bash
uv run $SCRIPT raw discover --args '{"query":"test","intent":"testing"}'
uv run $SCRIPT raw scrape_as_markdown --args '{"url":"https://example.com"}'
uv run $SCRIPT raw search_engine --args '{"query":"test","engine":"bing"}'
```

Full tool list: `discover`, `scrape_as_markdown`, `scrape_batch`, `search_engine`, `search_engine_batch`.

## Output handling

- Short results (up to 4 KB of text) print to stdout inline.
- Larger results spill to `~/.cache/bright-data-cm/<timestamp>-<label>.md` (or `.txt`). The script prints the file path and the first 1500 characters.
- Read the spilled file path with the `Read` tool when you need the full content.

## When to use this vs WebFetch

| Scenario | Tool |
|---|---|
| Simple, unprotected page | WebFetch |
| CAPTCHA or bot-protected page | use-bright-data |
| Search engine results (structured) | use-bright-data |
| AI-ranked web discovery | use-bright-data |
| Multiple URLs in one call | use-bright-data |
| Page behind Cloudflare/Akamai | use-bright-data |

**Rule of thumb:** Try `WebFetch` first for simple pages. If it returns a block page, CAPTCHA challenge, or empty content, switch to `use-bright-data`.

## Common mistakes

1. **Passing more than 5 URLs to batch-scrape or batch-search.** The Bright Data MCP enforces a max of 5 items per batch call. Split larger sets into multiple calls.
2. **Using this for library docs.** Use `/use-context7` instead -- it is faster and purpose-built for library documentation.
3. **Forgetting to read spilled output.** When the script prints a file path, use the `Read` tool to see the full content. The inline preview is truncated to 1500 characters.
4. **Missing API token.** The script exits naming the reader's failure: the reader not on PATH, or the reference in `settings.secrets.apiToken` not found.
5. **Empty results with no error.** A scrape returning an empty text block, or a search failing to parse JSON, usually means the Bright Data side is refusing rather than the page being empty: check `GET https://api.brightdata.com/status` for `can_make_requests`, and `GET /zone?zone=mcp_unlocker` for `plan.disable`.

## Performance notes

Bright Data routes requests through proxy infrastructure with anti-bot capabilities. Expect **5-30 seconds** per scrape call (sometimes longer for heavily protected pages). Batch calls run server-side in parallel but the MCP response waits for all to complete. The tool call timeout is set to 120 seconds to accommodate this.
