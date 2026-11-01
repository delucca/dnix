# Glyphs MCP 2.3.0 operation reference

This reference applies to the [signed 2.3.0 release](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.3.0). Read the running `get_status` capabilities and `describe` schema because the [tagged tool contract](https://github.com/thierryc/Glyphs-mcp/blob/v2.3.0/content/reference/command-set.mdx) has a stale 2.2.0 introductory sentence and an installation may have different coordinated component versions.

## Setup

Install Glyphs 4 and its official Python module through Window → Plugin Manager → Modules. Save open work and quit Glyphs normally before installing the bridge. Install the Glyphs MCP component from the [desktop app Setup](https://thierryc.github.io/Glyphs-mcp/docs/v2/getting-started/installation/), then reopen Glyphs. The signed desktop app includes its private sidecar runtime. The wrapper requires `uv` and Python 3.11 or newer; `uv run` installs its separate, exactly pinned `mcp==1.27.2` and `httpx==0.28.1` client dependencies on first use. Start the server from Edit → Glyphs MCP Server… and copy its loopback URL. The default is `http://127.0.0.1:9680/mcp/`; port 9681 is the private bridge, never the client endpoint. Installing the MCP component alone avoids Setup's unrelated inspector and persistent agent connectors.

Use `status` to check sidecar, bridge, worker, product identity, and capabilities. A connection error means the listener is absent or using another port. A connected sidecar can still report an unavailable bridge or unsupported operation. Updating the desktop app alone does not update Glyphs' installed component; coordinate versions in Setup when status disagrees.

## Identify and inspect

`list_documents` returns IDs for the open fonts, paths, dirty state, and an `isCurrent` marker when available. Retain the ID of the intended font rather than letting a later tab change retarget work. Rediscover after `document_not_found` or an explicit target change.

`read_entities` accepts an exact `document_id`, a list of selectors, and fields. For example:

```json
{"document_id":"DOCUMENT_ID","entities":[{"kind":"glyph","id":"b"}],"fields":["name","unicode","export"]}
```

Read master and layer inventories to get native IDs. Read layer width, bounds, metrics keys, and `outlineHash`; read path pages and node pages for geometry. Stored kerning and feature blocks have separate selectors. Follow `nextCursor` until `complete`, including after an empty page; restart a cursor after a change or stale-cursor error. A dirty or pathless font can be inspected without saving.

`create_document` opens an unsaved font with a Regular master and instance. `open_document` opens an absolute `.glyphs` or `.glyphspackage`; `import_document` accepts UFO, OTF, or TTF. Compiled imports are view-only until saved to a new native source. Retain the tool's idempotency key for the exact intended operation and its document ID for later calls. `duplicate_document` makes a separate unsaved copy when advertised.

## Edit and recover

Check `get_status` for the job kind and write capabilities. `start_edit_workflow` retains a task and can apply ordinary complete typed results; `mode="preview"` retains a preview request. `start_job` prepares a typed result without applying. Some typed jobs require a saved, clean baseline; `python_script` can run on dirty and pathless fonts when `script.native.v1`, `script.recovery.snapshot.v1`, and preparation version 3 are advertised. Ask `describe start_edit_workflow` for the live schema before building its arguments.

For native scripts, send `kind:"python_script"`, an idempotency key, exact document ID, mode, and `options` containing `source`, JSON `params`, `entrypoint` (`script` or `per_target`), `targets`, and optional summary. Keep targets tied to observed glyph/master/layer IDs. `executionMode` and `recovery` are retired. Preparing and polling do not execute code. An in-scope requested edit permits the offered Run action. A request to write code only or preview only stops before Run. Scripts run inside Glyphs and may affect the computer; the bridge's recovery covers font state, not external effects.

```json
{"document_id":"DOCUMENT_ID","kind":"python_script","idempotency_key":"one-intended-edit-unique-key","mode":"apply","options":{"source":"print('ready')","params":{},"entrypoint":"script","targets":[],"summary":"Inspect the current font"}}
```

After starting, call `get_edit_workflow` with its ID. Read the current revision and offered action token. Send only the offered action with `respond_edit_workflow`, then inspect the same workflow again. `get_edit_workflow(include_review=true)` exposes script details when needed. `list_tasks` locates unresolved work after a client disconnect. Keep the same key and arguments if the service explicitly supports an identical retry; otherwise inspect before any write. A script's successful execution does not itself verify the intended edit. Read the affected entities, inspect proof, and settle the workflow deliberately. `auto_keep=false` respects a request to wait for the person's answer; text-only clients do not automatically Keep.

For typed jobs, use `get_job` until terminal preparation. Read the full report before application; `include_preview:false` makes later polls smaller. `apply_job` mutates only a ready mutation result. `accept_job` persists an applied mutation, while `discard_job` cancels or restores where the affected targets remain current. Export artifacts have a different path below. A timeout or uncertain status calls for `get_job`/`get_edit_workflow`, not a replacement job.

## Proof, source, and export

`open_edit_tab` takes the document ID and a unique key, plus `text` or a list of exact glyph names and optional master ID. Its native tab gives a live visual proof, including for unsaved fonts. It does not save, export, or render an image file. The workflow card shows status and reports, but has no dedicated outline renderer. For file previews, use an advertised artifact or a documented native script and inspect the created image; do not assume a generic `render` MCP tool exists.

`save_document` saves an explicitly identified document when no job owns it. A pathless font needs a new absolute `.glyphs` or `.glyphspackage` destination. A job in applied/accepting state owns its save path; use the offered workflow action or `accept_job`. Saving writes the whole font. Inspect the receipt's path, verification, and source hashes, then verify the native file exists. Saving source is independent from exporting a compiled font.

For compiled export, first read instance IDs with `read_entities`, then check `font_export` and verification capabilities. `start_job` with `kind:"font_export"` takes an exact `instanceId`, `otf` or `ttf`, and supported containers. For example:

```json
{"document_id":"DOCUMENT_ID","kind":"font_export","options":{"instanceId":"INSTANCE_ID","format":"otf","containers":["plain"]}}
```

The worker writes a private staged artifact and verifies its font tables. Poll `get_job`; a ready `artifact` result is not an applied edit. Publish with `accept_job` and a new absolute destination directory, then verify the manifest and files. Do not call `apply_job` on an artifact. Keep the job ID across CLI invocations while the sidecar runs; service restarts can interrupt jobs. Workflow records persist for reconciliation but an interrupted service must not silently replay edits.

## Result interpretation

The CLI prints the whole MCP `CallToolResult` as JSON, including content, structured content, `isError`, and metadata. Glyphs data/action tools contain an application envelope: `{"ok":true,"data":…}` or `{"ok":false,"error":…}`. The wrapper exits nonzero on the latter when it appears in structured content or a text content block. Even `ok:true` may describe a pending, partial, cancelled, failed, or uncertain job; inspect its status and warnings before reporting completion. Large payloads spill to `~/.cache/glyphs-cm/` and the CLI prints the exact path.
