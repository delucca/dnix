---
name: use-figcraft
description: Read and edit FigCraft documents through the desktop app's local control port. Use for "inspect this FigCraft file", "edit layers/layout in FigCraft", render, save, or export a FigCraft design. NOT for Figma (use-figma) or VectorCraft (use-vectorcraft).
argument-hint: "[status|inspect|commands|run|call|render|save|export] [arguments]"
allowed-tools: Bash(python3 */use-figcraft/scripts/figcraft.py *), Read
disable-model-invocation: true
---

# Use FigCraft

Inspect and edit the document in the running FigCraft desktop app through its local control port.

Route `$ARGUMENTS` to the requested FigCraft task or matching CLI subcommand, then use the workflow below to verify its target and result.

## Setup

Use Python 3's standard library; the script needs no package install or MCP registration. FigCraft must have been launched with its opt-in listener, usually `--control 7980`. If `status` cannot connect, first check whether the app is already running without that listener. After the current session is saved and quit, launch with `open -a FigCraft --args --control 7980`. The port flag belongs to the app, not to this script.

```bash
python3 {baseDir}/scripts/figcraft.py status
```

The script makes one request per invocation. It prints the app's result as JSON on stdout and errors on stderr. Pass `--port 7980`, `--timeout 70`, and `--window ID` before the subcommand when needed. With no window, FigCraft targets the last frontmost window. `--window 0` explicitly targets the main window.

## Workflow

1. Run `status` to list windows, active tabs, and their IDs. Pick the intended window, then pass its ID on subsequent calls.
2. Run `inspect` and verify the document name and path before an edit. Tabs can change inside the same window, so inspect again after a tab switch.
3. Run `commands` to discover live command IDs and parameter descriptions. A query searches IDs, labels, and parameter descriptions; an exact ID returns its complete schema, including `undoable`. Read that field as metadata, not an enabled flag.
4. Make the requested change with `run` or, for a native control method, `call`. Use the parameter names returned by discovery. The CLI passes generic parameter trees through unchanged; give native methods absolute file paths where they require paths. Programmatic engine commands never open file dialogs, so provide explicit paths to file commands.
5. Inspect the result, then `render` a PNG and open it with `Read` for visual verification. Save or export to the requested location, and verify the file and document's path/dirty state when those properties matter.

## Commands

```bash
python3 {baseDir}/scripts/figcraft.py --window 0 inspect --depth 2 --all-pages
python3 {baseDir}/scripts/figcraft.py --window 0 commands rectangle
python3 {baseDir}/scripts/figcraft.py --window 0 commands shape.rectangle
python3 {baseDir}/scripts/figcraft.py --window 0 run shape.rectangle --args '{"x":10,"y":10,"width":100,"height":50}'
python3 {baseDir}/scripts/figcraft.py --window 0 run node.set --args - < params.json
python3 {baseDir}/scripts/figcraft.py --window 0 call node.get --args '{"id":2,"depth":2}'
python3 {baseDir}/scripts/figcraft.py --window 0 render './preview.png' --args '{"ids":[2],"scale":2}'
python3 {baseDir}/scripts/figcraft.py --window 0 save './design.figcraft'
python3 {baseDir}/scripts/figcraft.py --window 0 export './design.svg' --args '{"ids":[2],"format":"svg"}'
```

`inspect` defaults to depth 1; use `--all-pages` when other pages' layer trees matter. `render` draws the selection or current page's top-level layers unless `ids` selects layers. Its `scale` controls PNG size. The positional paths for `render`, `save`, and `export` become absolute paths from the current working directory, with `~` expanded; the script does not create parent directories. `--args` accepts a JSON object or `-` for stdin. A conflicting `path` in `--args` fails before connecting.

`save` invokes `file.save` synchronously. A `.figcraft` path saves the native document. A `.fig` path writes an experimental export copy and can return `warnings`; it does not update the native document path or clear unsaved changes. `export` invokes `file.export` synchronously and returns its format, path, and any warnings. Preserve warnings in the result you report. See the app's [control protocol](https://github.com/storytold/figcraft/blob/v0.10.0/docs/control-protocol.md) for native methods and `commands` for the running version's engine schema.

## Failure handling

- A connection error means nothing was sent. Check that FigCraft is listening on the selected port.
- A reply or timeout failure after transmission may mean the action ran. Inspect the app before retrying a write; the CLI never retries automatically.
- A missing expected file or a changed tab calls for `status` and `inspect` before the next write.

## Hard prohibitions

- Do not interrupt an open document to enable the listener; have the user save and quit before relaunching.
- Use `call` only for a method the user requested or the workflow needs. Execute `app.quit` only on an explicit user request because it discards unsaved changes.
- Use `--automation-read-root` and `--automation-write-root` only when their restriction on human GUI actions is intended too.
