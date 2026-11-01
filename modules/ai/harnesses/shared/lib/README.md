# `~/.config/ai/common/lib/`

The shared kernel: modules imported by more than one shipped skill, or by
shipped skills and a consumer's.
A module with a single consumer lives in that skill's `scripts/`.
Some adapters consolidated copies that had drifted; a new adapter belongs here
when at least two skills share its protocol. Nothing here is a general-purpose
utility bucket: each module is a named adapter with one job.

Scripts import these through `sys.path` shims, since nothing here is an
installed package: from `skills/<name>/scripts/`, this kernel is
`parents[3] / "lib"`.

## Transport adapters

Speak one protocol to one kind of remote thing.

| Module | Transport |
|---|---|
| `mcp_stdio.py` | Any MCP server spawned as a **subprocess**, over newline-delimited JSON-RPC 2.0 on its stdio. Used by use-chrome, use-pdf-reader and other MCP-backed skills. |
| `craft_control.py` | A Craft desktop app's **loopback control port**, one request per call. Used by use-figcraft and use-vectorcraft. |

## Output port

| Module | Role |
|---|---|
| `emit.py` | The single way a skill script returns a result. Short payloads print inline; large ones spill to a timestamped file under a per-skill cache dir and print a preview, so the calling agent can `Read` the rest. |

## Adding a module

It belongs in a lib only if it is a named adapter with one job (a transport, a
credential source, an output port) and at least two skills need it; it
belongs in THIS lib only if a shipped skill is one of them. A helper used by exactly one skill belongs in that skill's
own directory; a grab-bag `utils.py` belongs nowhere.
