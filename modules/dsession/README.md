# dsession

`dsession` starts or resumes a Codex, Claude Code or agy session with a list of linked project directories loaded. Each linked directory contributes its instructions (`AGENTS.md` or `CLAUDE.md`), its native skills (`.agents/skills`, `.claude/skills`), its hooks (`.codex/hooks.json`, `.claude/settings.json`) and, for agy, its Claude agents (`.claude/agents`), on top of the user's global configuration and the project in the working directory. The directories stay ordinary checkouts. It runs from a terminal or from an editor that passes the list. `dnix.dsession.enable` puts it on PATH.

## Files

```
default.nix              the home-manager module
dsession.py              the launcher, Python 3 standard library only
tests/test_dsession.py   the unit tests behind the flake check dsession
```

## Module

```nix
dnix.dsession = {
  enable = true;
  wrappers = [ [ "wrap" "agent" "run" "claude" ] ];
};
```

`wrappers` is written to `~/.config/dsession/config.json`; it is empty by default and then no file is written. `dnix.dsession.script` is read only: `dsession.py` with a `#!/usr/bin/env python3` line, for shipping the launcher to a machine that does not run this module.

## Usage

```
dsession new    [--dir PATH]... [--context FILE] -- CLIENT [ARGS...]
dsession resume ID [--dir PATH]... [--context FILE] -- CLIENT [ARGS...]
dsession trust  [--dir PATH]...
```

`trust` records which Claude hooks a linked directory may run, as described under Trust. It takes the directory list the same way and no client.

`CLIENT` is `codex`, `claude` or `agy`. With no linked directory and no context, `new` runs any client untouched, while `resume` or a linked directory with another client is a usage error. The `--` is required, and everything after `CLIENT` is passed to the client unchanged.

A wrapper is a command that runs a client for you, such as `wrap agent run claude`. Each one listed under `wrappers` in `$XDG_CONFIG_HOME/dsession/config.json` (`~/.config` when `XDG_CONFIG_HOME` is not an absolute path) is an argv whose last word is `codex`, `claude` or `agy`. When `CLIENT` and the start of `ARGS` match one, dsession runs that client's adapter and puts the wrapper's other words in front of the final command line. A missing file means no wrappers. A file that does not parse, or a wrapper that is not a list of at least two strings ending in a client, gets `dsession: ignoring unreadable FILE` and no wrapper applies. Without any `--dir`, the list comes from `DSESSION_DIRS`, a JSON array of strings. The two sources are never merged, and a malformed `DSESSION_DIRS` is a usage error.

Each path is expanded (`~`), joined to the launch directory when relative, normalized and resolved to its real path. A path that is not a directory is dropped with `dsession: skipping missing directory PATH`. Duplicates are dropped, first seen wins. When no directory is left and there is no context, the client runs untouched: no overlay, no extra flags, no extra environment.

The client is found on PATH. Diagnostics are one line each on stderr, prefixed `dsession: `.

| Exit code | Meaning |
|---|---|
| 2 | Usage error |
| 1 | The overlay could not be built or was refused, hook trust could not be seeded, or `trust` could not write its state file |
| 127 | The client is not on PATH |

`--context FILE`, or `--context=FILE`, names a file of text the session is born with, such as the task it was started on. It may appear once, anywhere among the `--dir` flags, and `trust` refuses it. The file is read once, at launch, as UTF-8. A file that holds only whitespace counts as no context. A file that cannot be read is skipped with `dsession: skipping unreadable context FILE` and the launch goes on without it. Text over 64 KiB is cut at the last newline before the limit, gets a final `[dsession: context truncated at 65536 bytes]` line, and dsession warns `dsession: context FILE truncated to 65536 bytes`. For `codex` and `claude` the context never reaches the overlay, since the overlay is shared by every session with the same list; `agy` is the exception, see the agy section. It is honoured with no linked directory too, for `codex`, `claude` and `agy`; with another client it is a usage error. agy cuts a rule file at 24 KiB, so for agy the limit is 24 KiB instead: the text is cut the same way, but the whole file, marker included, fits in 24576 bytes. The final line reads `[dsession: context truncated at 24576 bytes]` and the warning says `truncated to 24576 bytes`.

## Codex: the overlay home

Codex reads its global instructions, skills and hooks from `CODEX_HOME`, so dsession points `CODEX_HOME` at an overlay directory that looks like `~/.codex` with three entries replaced. The base home is `$CODEX_HOME` when it is set and not itself an overlay, else `~/.codex`.

The overlay lives at `/tmp/dsession-<user>/<hash>/`, where the hash is taken from the base home and the ordered directory list. The same list always gives the same overlay, and a different list or a different order gives a different one. Sessions with the same list share it.

```
/tmp/dsession-<user>/<hash>/
├── codex/                 CODEX_HOME for the session
│   ├── AGENTS.md          generated
│   ├── hooks.json         generated
│   ├── skills             a symlink to the current skills.<version>/
│   ├── skills.<version>/  generated, one symlink per skill
│   └── everything else    a symlink to the same name in the base home
├── claude/settings.json   the Claude adapter's generated settings
├── agy/                   the agy adapter's overlay folder, see the agy section
├── dirs                   the directory list, one per line, for reading only
└── lock                   held while the overlay is rebuilt
```

The overlay root, each list directory and the `codex`, `claude` and `agy` directories are created mode 0700 and the generated files 0600. dsession refuses a root or overlay directory that is a symlink or belongs to another user, with `dsession: refusing overlay root PATH (symlink or not owned by you)` or the same message naming the `overlay directory`, and exits 1. The Claude and agy adapters go through the same check and lock, so the refusal applies to every client. The client itself runs with the caller's umask.

Every `new` and `resume` rebuilds the overlay under the lock, in place. The overlay directory itself is never renamed or deleted, so sessions already running keep a stable `CODEX_HOME`. Every entry of the base home that is not generated, dotfiles included, becomes a symlink to it: `config.toml`, `auth.json`, `sessions/`, the sqlite databases and the rest. The one exception is `AGENTS.override.md`: Codex reads it instead of `AGENTS.md`, so a base one is never linked and dsession warns that it is ignoring it. A session written through the overlay is therefore a session in the real home, and `codex resume ID` from a plain shell finds it. Losing `/tmp` at reboot loses nothing.

`AGENTS.md` is the base `AGENTS.md` followed, for each linked directory in order, by its `AGENTS.md`, or its `CLAUDE.md` when it has no `AGENTS.md`, under a `# Linked directory: PATH` heading. Codex does not expand Claude `@` imports, so a `CLAUDE.md` with `@` lines gets a warning. A composed file over 32 KiB also gets a warning.

`skills` holds the base skills first, then each linked directory's `.agents/skills` and then `.claude/skills`. Every entry of the base `skills` folder is linked as it is. In a linked directory, a skill is a folder with a `SKILL.md`, named by its folder. When two sources carry the same name the first one wins and the later one is dropped with a warning naming both folders. Two entries that resolve to the same real path are the same skill and are dropped silently. `skills/.system` links to the base one when it exists. Names in `~/.agents/skills` count as taken, because Codex scans that folder itself. Each rebuild fills a new `skills.<version>` directory and then points the `skills` symlink at it with one rename, so a running session never finds `skills` missing on Linux. The previous version stays until the next rebuild, for a reader that already resolved the old link. On macOS a lookup that races the rename can still fail with EINVAL for that one call.

`hooks.json` is the base `hooks.json` followed by each linked directory's `.codex/hooks.json`. Per event, the hook groups are appended in that order and copied unchanged. Hook commands are copied verbatim, so a relative command path resolves against the session's working directory, not the linked directory: a hook meant to be linked should use absolute paths. A source that cannot be read or parsed is skipped with a warning.

Codex also gets `--add-dir DIR` for each linked directory.

A context reaches Codex as `-c developer_instructions=VALUE` after the `--add-dir` flags, where VALUE is a TOML basic string: quotes, backslashes and control characters are escaped and every other character is left raw. Codex sends it as a separate developer message. A `developer_instructions` set in `config.toml` is replaced for that session. A `-c` or `--config` override of the same key in `ARGS` comes later on the command line and wins, and dsession warns `dsession: pass-through developer_instructions overrides --context`. A resumed thread keeps the instructions it was born with, whatever a later launch passes. With a context and no linked directory, only the `-c` is added: no overlay is built and `CODEX_HOME` is left alone.

### Trust

Codex asks once to trust the hooks of a `hooks.json`, through `/hooks`, and keys that trust by the file's path. Since the overlay path is a pure function of the directory list, trust is asked once per list and kept: the answer is written through the `config.toml` symlink into the real `~/.codex/config.toml`, and the next launch with the same list finds it. A new list, a new order, or a switch that changes a global hook's command asks again.

dsession carries the trust already given to the global hooks over to each overlay. Codex records trust in `config.toml` under `[hooks.state]`, one entry per handler keyed by the hooks file path, the event, the group index and the handler index, with a hash that covers the handler and never the path. After writing the overlay `hooks.json`, dsession reads the base `config.toml` and takes every entry keyed by the base `hooks.json`, under its real path or as spelled, that has a `trusted_hash`. The base groups come first in the composed file, so the same group index names the same group in the overlay. When that group is identical to the base one and the overlay has no entry of its own yet, dsession adds one under the overlay's `hooks.json` path with the same hash. A global hook the user already trusted therefore runs in a new list without a `/hooks` prompt, and dsession prints `dsession: seeded trust for N global hooks into CODEX_HOME` when it added any.

Only trust recorded for the base `hooks.json` is carried over. A global hook the user never trusted, a global hook changed since it was trusted, and every hook from a linked directory still prompt through `/hooks`. The new entries are appended to the end of the real `~/.codex/config.toml`, following its symlink, through a temporary file and one rename that keeps the file mode. Launches with different lists take turns on `/tmp/dsession-<user>/hooks-trust.lock` for the append, so neither drops the other's entries. Codex itself does not take that lock, so a trust answer Codex writes in the same instant can still be lost and asked again. Existing content is never rewritten, and a second launch with the same list appends nothing. If the base `config.toml` is missing or does not parse, nothing is seeded, dsession warns `dsession: not seeding hook trust (config.toml unreadable)`, and the launch goes on. If the file no longer parses after the append, dsession puts the original bytes back, prints `dsession: could not seed hook trust in PATH` and exits 1.

Claude has no such prompt for hooks passed through `--settings`, so dsession asks instead, once per directory. `dsession trust --dir DIR` prints each directory whose `.claude/settings.json` has hooks, shows those hooks as JSON and asks `Trust these hooks? [y/N]`. Only `y` or `Y` typed on a terminal trusts them. Any other answer, or a stdin that is not a terminal, declines. A yes records the sha256 of the hooks in canonical JSON, keyed by the directory's real path, in `$XDG_STATE_HOME/dsession/claude-hooks.json` when `XDG_STATE_HOME` is an absolute path, else `~/.local/state/dsession/claude-hooks.json`. Its folder is created mode 0700. The file is replaced atomically and lives outside the overlay, so it survives a reboot. A launch includes a directory's hooks only while their hash matches the recorded one. Otherwise it skips them with `dsession: skipping untrusted Claude hooks in DIR (run: dsession trust --dir DIR)` and launches as usual. Editing the hooks therefore asks for trust again. Codex's own trust flow is unchanged.

### Strays

Codex is not expected to create regular files in the overlay, but if one appears where a symlink should be, the next rebuild moves it out rather than losing it. When the base home has no entry of that name, the file is moved there and dsession warns that it was adopted. When the base home already has one, the overlay copy is moved to `<base>/<name>.dsession-stray-<timestamp>` with a warning, and nothing is merged. A symlink that dangles or points elsewhere is replaced.

## Claude

Claude Code discovers skills and settings in added directories itself, so dsession leaves `~/.claude` alone and only builds the command line:

```
claude [--resume ID] [--add-dir DIR]... [--settings FILE] [--append-system-prompt TEXT] ARGS...
```

It sets `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` so each directory's `CLAUDE.md` is read, and `CLAUDE_CODE_NO_FLICKER=1` so Claude draws with its alt-screen renderer. The generated settings file, `claude/settings.json` in the overlay directory, holds the `hooks` of each linked directory's `.claude/settings.json` in order, for the directories whose hooks are trusted (see Trust), followed by any `--settings` found in `ARGS`. Those are removed from `ARGS` and merged in, so Claude sees a single `--settings`. A `--settings` value is a file path when that file exists, otherwise a JSON string, and one that cannot be read is dropped with a warning. A linked directory that has an `AGENTS.md` but no `CLAUDE.md` reaches Claude through `--append-system-prompt`, under the same heading Codex uses. Duplicate skill names get the same warning as for Codex, and nothing else is done about them.

A context goes into the same single `--append-system-prompt`, after those linked `AGENTS.md` blocks and before the text of any `--append-system-prompt` or `--append-system-prompt-file` found in `ARGS`. Those are removed from `ARGS` and merged in, blocks joined by a blank line, so Claude sees one flag; a file that cannot be read is dropped with `dsession: ignoring unreadable --append-system-prompt-file FILE`. `--system-prompt-snapshot` is left at Claude's default, so the prompt is fixed on the first request, and a resume still carries the context for the first request after a compaction.

## agy

agy loads, from each directory given with `--add-dir`, its `AGENTS.md`, `.agents/rules`, `.agents/skills`, `.agents/agents` and `.agents/hooks.json`, whether or not the directory is a git repository. It asks no trust question for them, in print mode (`agy -p`) or in the interactive terminal UI, whose trust dialog is about the working directory only. dsession leaves `~/.gemini` alone and builds the command line:

```
agy [--conversation ID] [--add-dir DIR]... [--add-dir OVERLAY] [--add-dir CONTEXT] ARGS...
```

There is one `--add-dir` per linked directory, so agy reads each directory's own files itself. `resume ID` becomes `--conversation ID`, with or without directories. agy starts a new conversation, with only a warning, when the id is unknown, so `resume` first checks that `~/.gemini/antigravity-cli/conversations/ID.db` exists (a dangling symlink counts as missing) and otherwise warns `dsession: agy conversation ID is not on this machine` and exits 1 without starting agy or writing any overlay. No environment is added. A linked directory with a `CLAUDE.md` and no `AGENTS.md` gets `dsession: agy reads AGENTS.md, not CLAUDE.md, in DIR`, since agy never reads `CLAUDE.md`. Claude hooks are not translated, and a linked directory's `.agents/hooks.json` is loaded by agy itself. Whether it needs a trust step of its own in the interactive UI has not been checked.

A `--context` reaches agy as a rules folder, since agy has no flag for text: the (24 KiB capped) text is written as `AGENTS.md` and the folder is passed with one more `--add-dir`, after the linked directories and the agents folder. agy loads an added directory's `AGENTS.md` as a rule. The folder lives in the overlay, under the lock:

```
/tmp/dsession-<user>/<hash>/agy-context/<key>/AGENTS.md
```

`<key>` is the first 16 hex digits of the SHA-256 of the context file's real path, so each task keeps its own folder and two sessions with the same list do not overwrite each other. The folders are 0700 and the file 0600, replaced atomically on every `new` and `resume`. A blank or unreadable file adds nothing: no folder and no flag. A context with no linked directory still goes through the overlay, with only this folder added. The folders are not cleaned up. agy started without dsession gets no context.

agy reads agents only in its own dialect, so the Claude agents in each directory's `.claude/agents` go through `agy-agent-md`, the program that also renders the global agents at build time and that must be on PATH. dsession passes it a fresh folder and the absolute path of every source. The result lives in the overlay:

```
/tmp/dsession-<user>/<hash>/agy/        passed to agy with --add-dir, last
├── .agents/agents                      a symlink to ../agents.<version>/
└── agents.<version>/<name>.md          written by agy-agent-md
```

Every `new` and `resume` with directories rebuilds it under the lock: a new `agents.<version>` is rendered, the `.agents/agents` link is swapped to it with one rename, and the versions other than the new one and the one the link held are removed. agy follows the link and reads the new target on its next start. The files are 0600 and the folders 0700. The folder is passed only when at least one agent was rendered, and a directory with no `.claude/agents` anywhere never runs the renderer.

A Claude agent is skipped when its file name is already taken, because agy would otherwise pick between the two without a documented rule. Names come from file names. First, every linked directory's own `.agents/agents/*.md` claims its names. Then each directory's `.claude/agents/*.md`, in directory order, is rendered unless the name is taken, in which case dsession warns `dsession: agent NAME from PATH dropped: already provided by OWNER`. Two entries that resolve to the same real path are one agent and the second is dropped silently. Two native agents of one name in two directories get `dsession: agent NAME in PATH collides with OWNER; agy picks one`. A project agent named like a global agent overrides it, as in Claude.

Rendering never blocks a launch. When `agy-agent-md` is not on PATH, dsession warns `dsession: agy-agent-md not on PATH; the linked directories' Claude agents are not loaded` and starts agy without the overlay folder. When it exits non-zero, its own stderr lines name each skipped file, dsession adds `dsession: some linked agents were not rendered for agy`, and the folder is passed with what was rendered. A refused or failed overlay exits 1 as for the other clients.

## Tests

`DSESSION_ROOT` replaces `/tmp/dsession-<user>` as the overlay root. It exists for tests, which point it, `HOME` and `PATH` at temporary fixtures and unset `XDG_STATE_HOME` and `XDG_CONFIG_HOME`, with a fake `codex`, `claude` and `agy` that log their arguments and environment.

```
nix flake check
```

runs them as the check `dsession`.
