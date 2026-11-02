# dnix

Keep this repository reusable: shared Nix modules, harnesses and skills belong here. Keep host configuration, personal identities, infrastructure addresses and consumer-specific secret references in the consuming flake. Use consumer options for those values.

Read [README.md](README.md) for the public module entry points and the relevant module README before editing. This flake has no host deployment workflow.

## Checks

Run checks from the repository root. The registered checks target `aarch64-darwin`:

```sh
nix flake check
nix build .#checks.aarch64-darwin.ai-dsession
```

The second command is an example of running one check; select the check relevant to the change from [flake.nix](flake.nix) or [modules/ai/tests/default.nix](modules/ai/tests/default.nix). Register new tests explicitly in those definitions; adding a test file alone does not run it.

Add new source files to Git's index before evaluating the flake, because untracked files are excluded from its source.

## AI changes

Keep shared skill helpers in `modules/ai/harnesses/shared/lib` only when several skills use them; otherwise keep them beside the skill. Follow [the helper ownership guide](modules/ai/harnesses/shared/lib/README.md).

After changing skill descriptions, run the `ai-codex-skill-budget` check. Consumers must check their installed skill set separately; this flake checks the shipped set.

Keep generated client configuration driven by `dnix.ai` options. Read [the AI module guide](modules/ai/README.md) for consumer settings and defaults before changing a harness.
