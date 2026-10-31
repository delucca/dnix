# Cross-harness audit (Step 7b)

Loaded at Step 7b. The two harnesses other than the running one read the finished review headless,
on their high-reasoning model, and report what they dispute, what they think was wrongly refuted,
and what the review missed. A different model family fails differently, which is the point; a second
refuter of the same family would buy correlation, not signal.

Contents: when; the input bundle; the prompt template; launch; reading the results; landing; isolation and data.

## When

Step 7b runs after the refuter's verdicts, or straight after Step 6 when the merged pool is empty
(the auditors may find what the lenses missed). It runs unless the token `no-audit` is present or
`REVIEW_CROSS_AUDIT=off` is in the environment, and it needs at least one available auditor. A
review then costs two headless high-reasoning runs in parallel (up to 15 minutes) plus a small
refuter pass.

## The input bundle

`B` is `<scratchpad>/review/audit/bundle/`, built once and never edited afterwards. `cross-audit`
copies it per auditor.

- `target.diff`.
- `findings.md` with three numbered lists: `C1..` confirmed (claim, location, evidence, grounding,
  the refuter's line), `R1..` refuted (claim, location, counter-evidence) and `U1..` unverified
  (claim, what would settle it). An empty list reads "none".
- The `diff-metrics bundle` outputs `tripwires.md`, `stat.txt` and the `pointers-*.txt` files. Never
  the raw `metrics.json`: its `target.repo` names the real repository.
- `claim.txt`.
- `files/<repo-relative path>`: the head-side content of every changed file that is not excluded or
  binary, from the worktree, the index or the head commit as the target says. Omit it for a remote
  target whose head is not local.

Rewrite every absolute path that starts with the toplevel to a repo-relative one while building the
bundle. `cross-audit` refuses a bundle that still holds the toplevel's path.

## The prompt template

Write it to `<scratchpad>/review/audit/prompt-template.md`. `cross-audit` renders it per auditor:
`{BUNDLE}` is that auditor's own copy, `{CLONE}` the clone path or `none`.

```
You are auditing a finished code review from a different model family. Read, judge, report. You change nothing.

Your inputs, all under {BUNDLE}:
- target.diff: the change under review
- findings.md: the review's findings (C = confirmed, R = refuted, U = unverified)
- tripwires.md, stat.txt, pointers-*.txt: deterministic measurements
- claim.txt: what the change claims to do
- files/: the changed files as they are after the change
A full checkout of the changed tree to read for context: {CLONE}

Rules: read only the paths above. Do not edit, create or delete any file; run no command that writes; never run the project's code (no tests, builds, scripts or package managers); no network; do not spawn agents. Cite only code you read.

Report exactly these four sections:

## Disputed
One line per confirmed finding you believe is wrong: `C<n>: <why>`, then `evidence: code: <path>:<line> "<quote>"` or `evidence: judgment`.

## Refuted but real
One line per refuted finding you believe holds: `R<n>: <why the refutation fails>`, then its evidence line.

## Missed
At most 10 issues the review did not report, located on lines of the diff, each:
    [SEVERITY] path:LINE — one-sentence claim
    evidence: `<exact quote>`
    grounding: code: <path>:<line> | judgment
    confidence: high | medium | low

## Checked
One or two sentences on what you examined.

Write "none" under a section with nothing in it.
```

## Launch

```bash
cross-audit run --harness <Step 1's answer> --bundle <B> --prompt-template <template> \
  --out <scratchpad>/review/audit/out --repo <toplevel> [--clone <clone>] [--untrusted] --timeout 900
```

Run it in the background and wait (SKILL.md Step 3b). A harness that kills the command at its tool
timeout sends SIGTERM: `cross-audit` then ends the auditors, marks them `interrupted` and still writes
its summary. SIGKILL cannot be handled, so keep the explicit timeout under the harness cap.

The auditors run in parallel on a read-only bundle, and 15 minutes bounds a hung or slow CLI
without blocking the review. A timeout reads `unavailable`, never clean.

Pass `--clone` only when a clone exists, which SKILL.md Step 3b allows for the user's own code only.
Pass `--untrusted` for every other target: only the Claude auditor, whose sandbox is enforced, runs, and
the others read `skipped (untrusted target, no sandbox)`. When `cross-audit` is not on PATH, run `python3 -I ~/.config/ai/common/skills/review/scripts/cross_audit.py`
in its place.

| Running harness | Auditors |
|---|---|
| Claude Code | Astra (`codex exec`), Argon (`agy -p`) |
| Codex | Opus (`claude -p`), Argon (`agy -p`) |
| agy | Opus (`claude -p`), Astra (`codex exec`) |
| unknown | every available harness |

`--repo` is the toplevel; for a target reviewed outside a repository, omit it: nothing is fingerprinted
then, and the audit is not discarded for it. Exit 2 means a path leak or a usage error: report the audit as
`unavailable (cross-audit refused: <its message>)` and fix the bundle only when the leak is a path you wrote.

`cross-audit` owns the flags, the timeouts, the environment and the routing through the harness
wrapper: when `~/.config/ai/settings/review.json` has `harnessWrapper` (a list of strings, e.g.
`["my-wrapper","agent","run"]`) and its first word is on PATH, Claude and Codex run as wrapper + name + args;
otherwise they run directly. The auditor's environment is an allowlist (PATH, HOME, locale, proxy and CA
settings, the harnesses' own auth variables, the prefixes listed in the same file's `passEnvPrefixes`, and
`SSH_AUTH_SOCK` on the wrapped route only), with `PWD` set
to its own folder; `CROSS_AUDIT_PASS_ENV` adds exact variable names for a site (never `SSH_AUTH_SOCK`,
`*_KEY_CMD`, `*_TOKEN` or `*_SECRET`, and ignored under `--untrusted`). Every auditor gets
its own copy of the clone, made without hard links, one auditor included: nothing an unsandboxed auditor
writes (even to an ignored path such as `node_modules/`) can reach the clone the Step 7b refuter runs in. Links that leave the bundle are refused (exit 2); links that leave the clone are not
copied and are listed in `integrity.json`; special files are skipped. The leak scan covers the bundle
and the clone's `.git` (not its objects), not the whole checkout. The previous output of each auditor
is cleared before it starts. It writes `<out>/<auditor>/audit.md`, a one-line `status`,
`<out>/summary.json` and `<out>/integrity.json`, and exits 0 when it ran cleanly, 2 for a usage error, a path leak or an unreadable fingerprint (those
auditors read `discarded (state unreadable)`), and 128 plus the signal number when interrupted.

## Reading the results

For each auditor with status `ok`, split `audit.md` by the four headings. A missing heading or an
unparseable line makes that auditor `unreadable` in the Audit line, with the path of its raw file.
Every other status goes into the Audit line verbatim.

`integrity.json` has `repo_changed`, `clone_changed`, `bundles_changed`, `clone_copies_changed` and
`interrupted`. A true `repo_changed` invalidates the review's evidence (Step 8). A changed bundle or
clone copy only discards that auditor's audit; a changed shared clone discards them all.

## Landing

- **A disputed confirmed finding stays confirmed**, marked `audit: disputed by <auditor> - <evidence>`
  with the auditor's evidence beside the refuter's. Demoting on one dissent would be the AND-gate
  this skill forbids: a finding never needs two lenses to agree, and the refuter's confirmation
  rests on code it re-read.
- **A refuted finding an auditor calls real moves to Unverified** as a contested refutation, both
  evidences shown. It does not go back to a refuter: asking the same family again buys correlation,
  and two families disagreeing on the same evidence is what UNVERIFIABLE means.
- **A missed issue goes through one refuter pass.** Deduplicate the issues from all auditors by
  location (Step 6's operations), write them to `candidates-audit-<n>.md`, and verify them with the
  refuter template: the verify model, one refuter, two above 15 candidates, split by file, and the
  same `Throwaway clone: <clone> | none` line as in Step 7. It is a new claim nobody has checked,
  and only a confirmed finding can block or reach a fixer. CONFIRMED joins the confirmed findings as
  `source: audit (<auditor>)`; REFUTED is listed under "Refuted during verification", tagged the same
  way; UNVERIFIABLE joins Unverified.
- The Verdict line keeps its shape; its counts include these moves.

## Isolation and data

No auditor gets the real repository, on any harness.

- Claude runs `--restricted` with only `Read`, `Grep` and `Glob`, no MCP server and no skills, so
  its file access ends at its bundle copy and its clone copy. This is enforced.
- Codex is asked for `-s read-only`, but on these hosts the managed
  `/etc/codex/managed_config.toml` sets `sandbox_mode = "danger-full-access"` and overrides it.
  `cross-audit` reports `(no read-only sandbox: managed policy)` in the status, because `codex doctor`
  shows the filesystem as unrestricted. The live smoke's write attempt was refused, so what Codex
  enforces at run time is unverified; on the wrapped route the note reads `(sandbox state unknown: wrapped
  route)`. The isolation is by path: its working directory is its bundle copy and nothing it is given names the real
  repository.
- agy runs `--sandbox` for its terminal, but its file tools are unrestricted and the host may allow
  non-workspace access, so it has the same residual risk as Codex.

The residual risk: an unsandboxed auditor that guesses a path can still read or write outside its
bundle. `cross-audit` fingerprints the real repository (HEAD, index entries, tracked and untracked
content; not ignored files or `.git`), the clone and each clone copy (the same, plus `.git/config`,
`hooks` and `info`) and hashes each bundle copy, before and after. Writes to those are caught and the
affected audits discarded; a write elsewhere, or to an ignored file of the real repository, is not.

On a host with a harness wrapper, Claude and Codex go through it, agy may not exist, and the diff reaches
whatever the wrapped Codex is configured to reach there. `REVIEW_CROSS_AUDIT=off` in the environment keeps the
code inside the running harness's provider; `no-audit` does it for one run.

A harness that sandboxes its own shell may block the auditor CLIs' network. That reads
`unavailable`, never clean.
