# ai

The agent stack for Claude Code, Codex and Antigravity CLI (agy): one set of skills, agents, hooks and instructions every harness loads, the harness files that link them in, and the `dsession` launcher. A flake takes `dnix.homeManagerModules.ai` for the user and `dnix.darwinModules.ai` for the policy files outside `$HOME`, and sets `dnix.ai.enable = true`.

## Files

```
default.nix        the options, the shipped skills and agents, ~/.config/ai
darwin.nix         darwinModules.ai: installs managed-settings.json and /etc/codex/managed_config.toml,
                   reading the primary user's dnix.ai options
harnesses/
  shared/          what every harness loads: skills/, agents/, hooks/, lib/, instructions/
  claude/          ~/.claude: skills, agents, CLAUDE.md, the managed settings, the no-MCP guard,
                   the CLI installer and patch-mode-badge
  codex/           ~/.codex: skills, AGENTS.md, agents rendered to TOML, hooks.json, managed config
  antigravity/     ~/.gemini: skills, AGENTS.md, agents rendered by agy-agent-md, hooks.json,
                   the settings merge, the no-MCP guard
dsession/          the linked-directory launcher, with its own README
tests/             the flake checks, each named ai-<test>; test files live beside their code
```

## How a consumer adds to it

Everything enters through options, and the harnesses render it. A consumer never writes a harness file.

- `dnix.ai.skills.<name>` and `dnix.ai.agents.<name>` take `{ enable, source, settings, packages }`. The shipped ones set `source` as a default, so a consumer overrides one by name, adds its own, or turns one off with `enable = false`. An entry with no source fails an assertion, which catches a misspelled name.
- `settings` renders to `~/.config/ai/settings/<name>.json`. `wrap-up` reads `ownRemotes` and `publishedTrailers` there, `review` reads `harnessWrapper` and `passEnvPrefixes`.
- `dnix.ai.instructions` and `dnix.ai.instructionDirs` take `NN-name.md` sections, merged with `harnesses/shared/instructions/` by number, the same shape as `dnix.developer`.
- `dnix.ai.claude.settings`, `dnix.ai.codex.settings`, `dnix.ai.codex.hooks`, `dnix.ai.antigravity.settings` and `dnix.ai.antigravity.hooks` take harness policy and hooks; lists from several modules are concatenated.

A skill script finds `lib/` by resolving its own path, so a consumer's skills sit in one store tree of their own and reach the shared libraries at `~/.config/ai/common/lib`. A shipped skill that needs a package carries a `packages.nix` returning a list, installed only while the skill is enabled. `programs.bilbo` comes from bilbo's own module: the shared instructions and the `docs-researcher` agent assume it is installed.

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.ai.enable` | `false` | Turns the module on. |
| `dnix.ai.skills` | the shipped skills | Skills every enabled harness loads, by name. |
| `dnix.ai.agents` | the shipped agents | Agents every enabled harness loads, by name. |
| `dnix.ai.instructions` | the shipped sections | Global instructions, concatenated by `order`. |
| `dnix.ai.instructionDirs` | `[ ]` | Folders of `NN-name.md` sections to add. |
| `dnix.ai.reviewLenses` | `[ ]` | Extra lens briefs for `review`, linked under `~/.config/ai/review-lenses/`. |
| `dnix.ai.skipPermissions.enable` | `true` | Runs every harness unattended: Claude's `bypassPermissions`, Codex's `approval_policy = "never"` with `danger-full-access`, agy's `always-proceed`. Turn it off on a machine where that is not wanted. |
| `dnix.ai.devTree` | `null` | A live checkout of `harnesses/shared` to link the shipped skills and `~/.config/ai/common` from, so an edit lands without a switch. Agents are rendered, so they always come from the store. |
| `dnix.ai.claude.enable` | `true` | Installs the Claude Code files and its managed settings. |
| `dnix.ai.claude.install.enable` | `false` | Runs `claude.ai/install.sh` at switch time when no `claude` is on PATH. |
| `dnix.ai.claude.patchModeBadge.enable` | `false` | Installs `claude-patch-mode-badge` and runs it at switch time: it strips the permission-mode badge and the idle "for agents" footer from the Claude binary, keeping its byte length. Each new version is patched once; a changed render site exits 2 with a warning. |
| `dnix.ai.codex.enable` | `true` | Installs the Codex files and its managed config. Run `codex doctor` after changing settings: Codex ignores an invalid managed value without a word. |
| `dnix.ai.antigravity.enable` | `false` | Installs the agy files and merges its settings. |
| `dnix.ai.dsession.enable` | `dnix.ai.enable` | Puts `dsession` on PATH. |
| `dnix.ai.dsession.wrappers` | `[ ]` | Commands that run a client through a prefix; see dsession's README. |
| `dnix.ai.dsession.script` | read only | `dsession.py` as a plain executable file, for a machine that does not run this module. |

## Skill descriptions are a shared budget

Codex renders every installed skill into one block capped at 2% of the model's context window (5440 tokens on a 272k model) and silently truncates descriptions once a profile stops fitting; Claude Code never truncates. Keep the `NOT for X (use-y)` clause, since bodies are invisible at selection time. `harnesses/codex/tests/codex-skill-budget.py` measures a list of skill folders: the `ai-codex-skill-budget` check runs it on the shipped set, and a consumer should run it on its installed set.
