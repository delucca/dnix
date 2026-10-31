# ai

The home-manager module for the agent stack. A flake takes it as `dnix.homeManagerModules.ai` and a host sets `dnix.ai.enable = true`. Today it carries `dsession`, the launcher that starts Codex, Claude Code or agy with linked directories loaded; see [its README](dsession/README.md).

## Files

```
default.nix      dnix.ai.enable, and the imports
dsession/        the linked-directory launcher, with its own README
tests/           the flake checks, each named ai-<test>
```

## Options

| Option | Default | What it does |
|---|---|---|
| `dnix.ai.enable` | `false` | Turns the module on. |
| `dnix.ai.dsession.enable` | `dnix.ai.enable` | Puts `dsession` on PATH. |
| `dnix.ai.dsession.wrappers` | `[ ]` | Commands that run a client through a prefix; see dsession's README. |
| `dnix.ai.dsession.script` | read only | `dsession.py` as a plain executable file, for a machine that does not run this module. |
