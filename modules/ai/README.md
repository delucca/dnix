# ai

One set of skills, agents and instructions for Claude Code, Codex and Antigravity CLI (`agy`). The Home Manager module renders each client's files and installs [dsession](dsession/README.md) for sessions spanning several directories.

## Enable it

Add this module to a Home Manager configuration that receives `inputs` through `extraSpecialArgs`, as shown in the [root guide](../../README.md):

```nix
{ inputs, ... }:
{
  imports = [ inputs.dnix.homeManagerModules.ai ];
  dnix.ai = {
    enable = true;
    skipPermissions.enable = false;
  };
}
```

`skipPermissions.enable` defaults to `true`: Claude uses `bypassPermissions`, Codex uses `approval_policy = "never"` with `danger-full-access`, and agy uses `always-proceed`. The example disables that default. Claude and Codex configuration are enabled by default; enable agy with `dnix.ai.antigravity.enable = true`.

On macOS, also import `dnix.darwinModules.ai` into the nix-darwin configuration. It installs policy files outside the home directory using the primary user's Home Manager options. The consumer supplies the client executables; Claude's optional installer is configured in [its module](harnesses/claude/default.nix).

## Customize through options

Add or override `dnix.ai.skills.<name>` and `dnix.ai.agents.<name>` with `source`, `settings` and `packages`; disable an entry with `enable = false`. A source is a skill directory or a Claude-format agent file. Settings render to `~/.config/ai/settings/<name>.json`. The harnesses own their generated files.

Skills with a `secrets.nix` or `requires.nix` are disabled by default. Enable them after supplying their required settings. Secret-reading skills also need `dnix.ai.secrets.readCommand`, or [op-agent](op-agent/default.nix); the [credential helper](harnesses/shared/lib/credential.py) reads references at use time.

Global instructions are ordered sections in `dnix.ai.instructions`, or `NN-name.md` files supplied through `instructionDirs`. Disable a shipped section by its name without the numeric prefix. Client-specific settings and hooks live under `dnix.ai.claude`, `dnix.ai.codex` and `dnix.ai.antigravity`.

Normally, shared files come from the Nix store. Set `dnix.ai.devTree` to a live `harnesses/shared` checkout for skill and helper edits without a switch. Agents are rendered per client and still come from the store. The shared instructions and `docs-researcher` agent expect the consumer to install bilbo separately.

## Find the definitions

| Concern | Source |
|---|---|
| Skills, agents, instructions and shared settings | [default.nix](default.nix) |
| Claude configuration | [harnesses/claude](harnesses/claude/default.nix) |
| Codex configuration | [harnesses/codex](harnesses/codex/default.nix) |
| agy configuration | [harnesses/antigravity](harnesses/antigravity/default.nix) |
| macOS policy installation | [darwin.nix](darwin.nix) |
| Linked-directory sessions | [dsession](dsession/README.md) |
| Helpers shared by skill scripts | [shared/lib](harnesses/shared/lib/README.md) |

## Check changes

From the repository root:

```sh
nix flake check
```

The [AI checks](tests/default.nix) register tests beside their implementations. The `ai-codex-skill-budget` check measures the shipped skill descriptions; consumers should also check their full installed set with the [budget script](harnesses/codex/tests/codex-skill-budget.py). Keep routing descriptions short, including their exclusions, because Codex can truncate the skill list when it exceeds its description budget.
