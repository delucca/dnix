---
name: use-glyphs
description: Read and edit fonts in the running Glyphs 4 app. Use for "inspect this Glyphs font", "draw or adjust glyph outlines", "change spacing, kerning, or features", "proof this word", save native source, or export a font. Use the live Glyphs MCP tool catalog for the requested font task. NOT for another drawing app or offline font-file conversion.
argument-hint: "[font task | status | documents | tools | describe TOOL | call TOOL --args JSON]"
allowed-tools: Bash(uv run */use-glyphs/scripts/glyphs.py *), Read
disable-model-invocation: true
---

# Use Glyphs

Read and edit an explicitly identified font in the running Glyphs 4 app through the local Glyphs MCP server.

Route `$ARGUMENTS` to a CLI command or carry out the described font task with the workflow below. The wrapper opens one MCP session per command and returns the complete tool result, including application status and errors.

```bash
uv run {baseDir}/scripts/glyphs.py status
uv run {baseDir}/scripts/glyphs.py documents
uv run {baseDir}/scripts/glyphs.py tools [query]
uv run {baseDir}/scripts/glyphs.py describe TOOL
uv run {baseDir}/scripts/glyphs.py call TOOL --args '{"document_id":"…"}'
uv run {baseDir}/scripts/glyphs.py call TOOL --args - < params.json
```

Set `--url http://127.0.0.1:PORT/mcp/` and `--timeout SECONDS` before the command if Glyphs uses another local port or a longer operation. `--args` accepts one JSON object; nested values and absolute paths pass through unchanged. Large replies spill to a private cache path printed by the wrapper. Read that file when a preview is insufficient. Tool errors exit nonzero and retain their complete reply.

## Workflow

1. Call `status` and `documents`. Check bridge availability and the live capabilities. Bind the intended font by its returned document ID, family, path, and dirty state; keep that ID through subsequent calls. An absent bridge needs the [setup steps](references/protocol.md).
2. Call `tools` or `describe TOOL` for the current schema, then `read_entities` for the exact glyphs, layers, master IDs, paths, feature blocks, or kerning involved. Paginate bounded inventories. Use current geometry hashes and IDs when an operation requires them.
3. Choose an advertised typed edit (`outline_edit`, `kerning_edit`, `spacing`, `native_action`, and related job kinds) when it expresses the change. For work needing native Python, use `start_edit_workflow` with `kind="python_script"` only when `status` advertises its script and recovery capabilities. Review script source and targets before submitting. A requested edit authorizes the in-scope Run action; use `mode="preview"` and wait when the person specifically asked for a preview or review.
4. Retain the returned job or workflow ID. Read `get_job` or `get_edit_workflow` until its state is clear; send only a currently offered `respond_edit_workflow` action with that workflow's revision and token. Use `list_tasks` to rediscover unresolved work. Never replay an uncertain mutation with a fresh key. Read back the changed entities and examine any report, warnings, partial results, and visual proof.
5. Use `open_edit_tab` for native text or exact-glyph proofs. Save editable source with `save_document` for an unowned document or the owning workflow/`accept_job` path for an applied job. Export compiled fonts through an advertised `font_export` job and publish its verified artifact with `accept_job`. Check the receipt and resulting file. Treat preparation, live application, source Save, and export as distinct outcomes.

For the detailed job lifecycle, script arguments, proof limits, and [Glyphs MCP 2.3.0 contract](references/protocol.md), read the reference when that operation is needed. For native Python objects and methods, check the [Glyphs Python API](https://docu.glyphsapp.com/) before writing a script.

## Failure handling

The wrapper may complete an MCP call that contains `ok:false` in its application payload, or a job that remains pending, failed, or uncertain. Inspect the full result and the original document, task, or workflow when the reply is lost. A connection failure before any tool call points to the setup steps in the reference.

## Hard prohibitions

- Do not quit or relaunch Glyphs to enable the server while the person's documents remain open.
- Do not replay a write after an uncertain result; reconcile the original job or workflow first.
- Do not report a prepared, pending, failed, or uncertain operation as a saved source or exported font.
