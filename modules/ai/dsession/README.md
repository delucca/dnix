# dsession

Start or resume Codex, Claude Code or agy with instructions, skills and hooks from linked directories. Each directory stays an ordinary checkout, and the client's normal session storage remains in use.

## Use it

The [AI module](../README.md) installs `dsession`; `dnix.ai.dsession.enable` can enable it independently. The client executable must be on `PATH`.

```sh
dsession new --dir ../other-project -- codex
dsession resume SESSION_ID --dir ../other-project -- claude
dsession new --dir ../other-project --context task.txt -- agy
dsession trust --dir ../other-project
```

Replace the example directory, session ID and context file with your own. Repeat `--dir PATH` for several directories. `new` and `resume` require `--` before the client command; client arguments follow it. `trust` takes directories and no client.

Without `--dir`, the launcher reads `DSESSION_DIRS` as a JSON array of paths. Relative paths resolve from the launch directory; missing directories are skipped and duplicate real paths are removed. Explicit directories replace the environment list. With no directories or context, `new` passes the command through unchanged.

For a command that wraps a client, configure `dnix.ai.dsession.wrappers`, for example `[ [ "wrap" "agent" "run" "claude" ] ]`. The launcher reads these prefixes from `dsession/config.json` under the absolute `XDG_CONFIG_HOME`, or `~/.config`. The [option definitions](default.nix) also expose `script`, a standalone Python 3 launcher.

## What each client loads

| Client | Linked-directory behavior |
|---|---|
| Codex | Composes global and linked `AGENTS.md`, skills from `.agents/skills` and `.claude/skills`, and `.codex/hooks.json` into a temporary `CODEX_HOME`. Converts `.claude/agents` through `codex-agent-toml` when it is on `PATH`, beside the global agents; with nothing to convert, `agents` links the real home's folder. Falls back to `CLAUDE.md` when `AGENTS.md` is absent, but does not expand its `@` imports. |
| Claude | Uses `--add-dir` and enables reading the directories' `CLAUDE.md`. Appends `AGENTS.md` when no `CLAUDE.md` exists. Merges trusted `.claude/settings.json` hooks with explicit client settings. |
| agy | Passes directories with `--add-dir`, leaving their native `AGENTS.md` and `.agents` files to agy. Converts `.claude/agents` through `agy-agent-md` when it is on `PATH`; it does not translate Claude hooks or `CLAUDE.md`. |

Codex keeps the first skill of a given name and warns about later collisions. Claude gets collision warnings but resolves its own skills. For agy agent conversion, native agent names take precedence over converted Claude agents. For Codex, global agent names take precedence, then the first linked directory; a converted agent keeps only its name and instructions, so its Claude tool list does not restrict it.

## Trust

Codex uses its own hook trust flow. The launcher carries recorded global hook trust into a new overlay, while linked-directory hooks still require Codex's approval. The overlay path depends on the base home and ordered directory list, so changing that list changes the trust location.

Claude hooks supplied through generated settings are gated by `dsession trust --dir PATH`. It displays the hooks and requires `y` or `Y` on a terminal. Untrusted or changed hooks are skipped during launch. Decisions persist in `dsession/claude-hooks.json` under the absolute `XDG_STATE_HOME`, or `~/.local/state`.

`dsession trust` applies only to Claude hooks. The launcher passes agy's native directory hooks through to the client without its own trust check.

## Context and resume

`--context FILE` reads UTF-8 text at launch. Blank text adds nothing; unreadable files are skipped with a warning. Text is capped at 64 KiB for Codex and Claude, and 24 KiB for agy, with a truncation marker.

Codex receives context through `developer_instructions`; a later client `-c` override of that key wins. Claude receives it through `--append-system-prompt`, merged with explicit prompt arguments. agy receives a generated `AGENTS.md` in an extra directory. Resume uses the client's native session ID and does not promise to replace instructions already stored in a conversation.

`resume ID` maps to `codex resume ID`, `claude --resume ID` or `agy --conversation ID`. For agy, the launcher checks that `~/.gemini/antigravity-cli/conversations/ID.db` exists first, because agy otherwise starts a new conversation for an unknown ID.

## Persistence

Generated files live under `/tmp/dsession-<user>/`. Codex's overlay links ordinary configuration and session storage back to its base home, so sessions remain available from a plain `codex resume` after the temporary files disappear. Three entries stay per overlay instead: `app-server-daemon` and `app-server-control`, because Codex refuses a symlinked daemon directory, and `secrets`, because Codex binds stored credentials to the resolved `CODEX_HOME`. Each overlay therefore signs in once, and signs in again after `/tmp` is cleared. Claude and agy retain their normal homes. Each launch rebuilds the needed generated files.

The launcher refuses overlay directories owned by another user or represented by symlinks. Its diagnostics go to stderr with a `dsession:` prefix. See [dsession.py](dsession.py) for overlay composition and failure handling.

## Checks

From the repository root on `aarch64-darwin`:

```sh
nix build .#checks.aarch64-darwin.ai-dsession
```

The [tests](tests/test_dsession.py) use temporary homes and fake clients to check arguments, overlays, trust and persistence. They are registered in [the AI checks](../tests/default.nix).
