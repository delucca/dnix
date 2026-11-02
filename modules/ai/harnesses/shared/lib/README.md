# Shared skill helpers

These Python modules provide adapters used by several skills. They are installed at `~/.config/ai/common/lib/` by the [AI module](../../../README.md).

| Helper | Responsibility |
|---|---|
| [mcp_stdio.py](mcp_stdio.py) | Starts a subprocess MCP server and exchanges JSON-RPC messages over its standard input and output. |
| [craft_control.py](craft_control.py) | Sends one request to a Craft desktop app's loopback control port. |
| [credential.py](credential.py) | Reads skill settings and runs the configured secret reader on a secret reference at use time. |
| [emit.py](emit.py) | Prints short results inline and writes large results to a caller-selected directory with a preview. |

## Use and ownership

The helpers are not an installed Python package. Skill scripts add this directory to `sys.path`, resolving it relative to their own file. From `skills/<name>/scripts/<script>.py`, the shared directory is `Path(__file__).resolve().parents[3] / "lib"`. See [the FigCraft client](../skills/use-figcraft/scripts/figcraft.py) for an existing caller.

Keep a helper in its skill's `scripts/` directory when only that skill needs it. A helper belongs here when at least two skills need the same adapter and at least one ships with this module. Each module owns one transport, credential source or output adapter; avoid a general-purpose utility collection.

## Checks

From the repository root on `aarch64-darwin`:

```sh
nix build .#checks.aarch64-darwin.ai-credential
```

[Credential tests](tests/test_credential.py) cover settings and secret-reader failures. The Craft adapter is exercised by the [FigCraft](../skills/use-figcraft/tests/test_figcraft.py) and [VectorCraft](../skills/use-vectorcraft/tests/test_vectorcraft.py) tests. These checks are registered explicitly in [the AI test definitions](../../../tests/default.nix).
