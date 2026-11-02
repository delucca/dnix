---
name: use-vectorcraft
description: Read and edit the open VectorCraft desktop document through its native control port. Use for "draw in VectorCraft", "edit this vector artwork", "inspect my VectorCraft document", or render, save, and export work there. NOT for FigCraft files (use-figcraft).
argument-hint: "[status|inspect|commands|run|call|render|save|export] [command, method, or path]"
allowed-tools: Bash(python3 */use-vectorcraft/scripts/vectorcraft.py *), Read
disable-model-invocation: true
---

# Use VectorCraft

Read and edit the active VectorCraft desktop document through its native control port.

If `$ARGUMENTS` names a wrapper command, run it with those arguments; if it describes artwork to create or edit, follow the workflow below to choose live commands and make the requested change.

## Requirements

- Use Python 3 with the standard library. No package install is needed.
- Use the VectorCraft desktop app started with its native control listener, for example `open -a VectorCraft --args --control 7979` after the person has saved and quit any existing instance. A running instance without the listener cannot gain it in place. Do not quit, relaunch, or change a person's open documents as part of setup.
- The listener is on `127.0.0.1`, has no authentication, and should be enabled only while needed. The app can optionally start with `--automation-read-root <directory>` and `--automation-write-root <directory>` to confine automation file access. With neither kind set, automation file access is unrestricted; once either kind is set, an omitted kind grants no access of that kind.

## Commands

```bash
python3 {baseDir}/scripts/vectorcraft.py status
python3 {baseDir}/scripts/vectorcraft.py inspect
python3 {baseDir}/scripts/vectorcraft.py inspect --args '{"depth":2,"childLimit":30}'
python3 {baseDir}/scripts/vectorcraft.py commands
python3 {baseDir}/scripts/vectorcraft.py commands rectangle
python3 {baseDir}/scripts/vectorcraft.py commands "$COMMAND_ID"
python3 {baseDir}/scripts/vectorcraft.py run "$COMMAND_ID" --args "$JSON_PARAMS"
python3 {baseDir}/scripts/vectorcraft.py call document.inspect --args '{"depth":2}'
python3 {baseDir}/scripts/vectorcraft.py render ./preview.png --args '{"artboard":0,"scale":2}'
python3 {baseDir}/scripts/vectorcraft.py save ./drawing.vectorcraft
python3 {baseDir}/scripts/vectorcraft.py export ./drawing.svg --args '{"format":"svg"}'
```

Set `COMMAND_ID` and `JSON_PARAMS` from the live command catalog; the example does not assume a particular command exists or accepts particular fields. Use `--port N` and `--timeout SECONDS` before the subcommand when needed. `--args -` reads a JSON object from standard input. The script resolves positional output paths against the caller's working directory. For file paths inside arbitrary `run` or `call` parameters, pass absolute paths because those parameters go to the app unchanged.

`status` calls `ui.inspect`. `inspect` calls `document.inspect` with a bounded depth of 1 and child limit of 20 by default. `commands` reads `engine.commands`; an exact ID prints its complete live schema and enabled state, and other searches return compact ID, label, and enabled matches. `run` calls `engine.execute` with the named command and its JSON parameters. `call` sends any native control method with its JSON parameters. `render`, `save`, and `export` call `ui.render`, `app.save`, and `app.export` with an absolute output path. The last two retain their other options from `--args`.

The stdout value is the native JSON `result`, including `null`, arrays, warnings, pending states, and background status. Backend errors go to stderr and exit nonzero. A successful exit means the app accepted and answered the request; it does not prove an asynchronous file write has finished.

`--args` must contain a JSON object. A path in `render`, `save`, or `export` is set by the positional path; if `--args` also contains `path`, it must resolve to the same file. An absent path in these commands is rejected by the parser. The generic `call` and `run` forms keep their parameter objects unchanged, including paths and nested options.

Choose the narrowest entry point for the task:

| Need | Command | Native method |
|---|---|---|
| Confirm the UI and background work | `status` | `ui.inspect` |
| Read the document tree | `inspect` | `document.inspect` |
| Discover executable commands | `commands [query]` | `engine.commands` |
| Execute a discovered command | `run ID --args JSON` | `engine.execute` |
| Reach another documented method | `call METHOD --args JSON` | That method |
| Write a PNG preview | `render PATH --args JSON` | `ui.render` |
| Write the native document | `save PATH --args JSON` | `app.save` |
| Export a format | `export PATH --args JSON` | `app.export` |

## Workflow

1. Run `status` to confirm the listener and identify the active document. A request acts on what is open in the app.
2. Run bounded `inspect` to locate the objects and state relevant to the request. Increase depth or use `ids`, `kind`, `limit`, and `offset` when needed.
3. Search `commands` by task, then query the exact command ID to read its live parameters and enabled state. For methods outside `engine.execute`, use the [native control protocol](https://github.com/storytold/vectorcraft/blob/v0.16.0/docs/control-protocol.md) and `call`; pass the documented JSON unchanged.
4. Make the requested edit with `run` or `call`. Check the returned result for pending dialogs, cancellation, warnings, or errors before treating it as complete.
5. Inspect again. For visual work, `render` to a PNG and read the image. Use a file path for `ui.render` so its reply stays small; `data: true` adds inline base64 when explicitly needed.
6. Save or export only as requested. A result with `background: true` means writing has started, not finished. Check `status` for running background jobs and inspect the output file after the job completes. Keep pending dialogs and cancellations visible to the user rather than reporting a completed file.

## Read, edit, and verify examples

For a read, start with `status` and `inspect`. If the initial tree omits the needed node, query a deeper level or a narrow slice instead of dumping the whole document:

```bash
python3 {baseDir}/scripts/vectorcraft.py inspect --args '{"ids":["node-id"],"depth":1,"childLimit":20}'
```

Use an ID seen in the actual inspect result. The native method also accepts `kind`, `limit`, and `offset` for sliced node lists. Keep the result tied to the currently active document; a tab change in the app changes what the next request reaches.

For an edit, find the operation by label, read its exact ID, and copy only parameters its schema names. Run it once. If a command returns `{"pending":"..."}`, inspect the open dialog and continue only according to the user's requested outcome. A `"cancelled"` result means the operation did not finish. If a reply was lost, inspect before another write because the first request may already have changed the document.

For visual verification, render the chosen artboard to an output PNG and open that PNG with the available image reader. `artboard` is zero based and `scale` controls rendering size. Rendering to a file avoids bringing an inline PNG into the conversation. If the change affects another artboard, select that artboard explicitly.

For saving, keep the native result. VectorCraft can write on a worker thread with the default background preferences. A `{ "background": true }` reply marks the job as started. `status` exposes the current background list; after it clears, check that the expected file exists and inspect any surfaced warning or error. Do the same for export, including exports that write several artboard files. A pending file dialog or replacement confirmation needs an explicit next action before a file is considered written.

When `status` shows a file dialog, inspect its state before continuing. A direct path usually avoids a native picker. If a request returns a confirmation dialog, use the native `ui.dialog.*` methods through `call` only when the user's requested operation determines how to answer it. For example, `python3 {baseDir}/scripts/vectorcraft.py call ui.dialog.cancel` cancels the open dialog; `call ui.dialog.confirm` accepts it. Report the resulting state from another `status` or `inspect` call.

The control protocol's `engine.execute` reports unknown parameter keys before a command runs. Correct the key from the live schema and issue a new request. When a known command is disabled, inspect the current document, selection, or tool state rather than guessing a different command. This keeps edits tied to the app's actual state.

## Troubleshooting

| Symptom | Next step |
|---|---|
| Cannot connect; nothing sent | Confirm the app was started with `--control` on the chosen port. Preserve open work before any manual restart. |
| Reply failed after transmission may have begun | Inspect the document or output before retrying; the action may already have run. |
| Unknown command or parameter | Read `commands` for the exact live ID and schema. |
| A file was accepted but is absent | Check `status` for a background job, a pending dialog, cancellation, or an app error before claiming completion. |

## Boundaries

Use the native desktop control channel. It exposes read and write methods, including generic `run` and `call`; use them only for the user's requested work. Keep responses and command parameters grounded in the running app and the linked protocol. The wrapper makes one request per process invocation and never restarts the app or retries an uncertain edit.

## Hard prohibitions

- Do not quit or relaunch the app while a person's documents may be open.
- Do not retry a write after a lost reply until the app state shows whether it ran.
- Do not report a background, pending, or cancelled write as a completed file.
