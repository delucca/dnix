---
name: use-pdf-reader
description: Reads text, metadata, images and page counts from local or remote PDFs. Use for reading a PDF path or URL. NOT for extraction the built-in Read tool covers.
allowed-tools: Bash(uv run *), Read
argument-hint: "[read|raw] [path_or_url] [options]"
---

# use-pdf-reader — on-demand PDF extraction via pdf-reader MCP

Read text, metadata, images, and page counts from local or remote PDFs without keeping the MCP registered permanently. The wrapper spawns `@sylphx/pdf-reader-mcp` as a short-lived stdio subprocess, runs one tool call, then terminates it. The main agent context stays clean.

## When NOT to use this skill

- **Simple text extraction** — the built-in `Read` tool already handles basic PDF text extraction; reach for this skill only when you need page-specific extraction, metadata, embedded images, or URL-based reading.

**Why this design.** Installing pdf-reader-mcp via `~/.claude.json` injects its tool schema into every conversation — even when no PDFs are involved. This skill loads nothing until you invoke it, and cleans up immediately after.

**No prerequisites.** The only dependency is the `pdf-reader-mcp` server: dnix's ai module puts a packaged one on PATH, and the script falls back to `npx` on the pinned package elsewhere. No API keys, no running browser, no background services.

## Usage

All subcommands run through one script:

```bash
SCRIPT={baseDir}/scripts/pdf-reader.py
```

### Read a PDF (local file)

```bash
uv run $SCRIPT read /path/to/document.pdf
uv run $SCRIPT read /path/to/document.pdf --pages "1-5"
uv run $SCRIPT read /path/to/document.pdf --metadata
uv run $SCRIPT read /path/to/document.pdf --images
uv run $SCRIPT read /path/to/document.pdf --page-count
uv run $SCRIPT read /path/to/document.pdf --pages "1-3" --metadata --page-count
```

### Read a PDF (URL)

```bash
uv run $SCRIPT read https://example.com/report.pdf
uv run $SCRIPT read https://example.com/report.pdf --pages "1-10"
```

The script auto-detects whether the argument is a local path or a URL.

### Escape hatch

Any tool exposed by pdf-reader-mcp is reachable via `raw`:

```bash
uv run $SCRIPT raw read_pdf --args '{"sources": [{"path": "/tmp/doc.pdf"}], "include_metadata": true}'
```

## Output handling

- Short results (<=4 KB text) print to stdout inline.
- Larger results save to `~/.cache/pdf-cm/<timestamp>-<op>.json` — the path is printed along with the first 1500 characters.
- Read saved paths with the `Read` tool to see the full content.

## Common mistakes

1. **Using the built-in Read tool for PDFs.** The built-in `Read` tool handles basic text extraction and is fine for simple cases. Use this skill when you need page-specific extraction, metadata, embedded images, or URL-based reading.
2. **Forgetting `uv run` prefix.** The script uses `#!/usr/bin/env -S uv run --script` — always invoke it via `uv run`.
3. **Passing page numbers as strings to --pages.** The `--pages` flag accepts range strings like `"1-5"` or comma-separated like `"1,3,7"`. Single pages work too: `"3"`.

## Dependencies

- `pdf-reader-mcp` on PATH (nix-packaged), or `npx` as the fallback; the script finds either via `shutil.which`.
- `uv` must be on PATH (for the `uv run --script` shebang).
- No API keys or secrets required.

## Design notes

**No persistent subprocess.** The MCP subprocess starts, handles one request, and terminates. No state leaks between calls.

**Portable resolution.** The script prefers a packaged `pdf-reader-mcp` on PATH and otherwise uses `shutil.which("npx")`, so it works on nix machines, devpods and system installs alike.

**Pinned MCP version.** The script uses `@sylphx/pdf-reader-mcp@2.1.0` to ensure reproducible behavior. Update the version in the script when upgrading.

**Output spills to `~/.cache/pdf-cm/`.** PDFs can produce large text output. The 4 KB inline limit keeps agent context manageable while the spill file preserves full content for follow-up reads.
