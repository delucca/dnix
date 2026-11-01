
---

## SECRETS

**Read secrets at use time. Never hardcode one, never echo one into the transcript.**

`op-agent` is a read-only service-account wrapper. It sees the **@vault@** vault and nothing else, and it never prompts.

1. **Try `op-agent` first** - `op-agent read "op://@vault@/<item>/<field>"`. Silent, no approval, no Touch ID.
2. **Not in @vault@? Fall back to `op`** - plain `op read "op://<vault>/<item>/<field>"` reaches every vault, but prompts the user through the desktop app.
3. **`op` failed? Stop and warn.** The failure means the user isn't at the machine to approve the prompt. Say which ref you needed and wait - don't retry, don't route around it.

Both binaries need unsandboxed Bash; in the sandbox `op` always reports "not signed in". Judge the result by its output, not its exit code - `op` prints `authorization timeout` and still exits 0.

**Report every @vault@ miss.** Whether or not the fallback worked, name the `op://` refs you had to read outside @vault@ in your closing message, so the user can decide whether to move them in. This is a report, not a question - never block on it.
