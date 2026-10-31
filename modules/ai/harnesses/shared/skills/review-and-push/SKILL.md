---
name: review-and-push
description: Gates a change (lint, tests, coverage, deep review), fixes what it finds, then commits and pushes. Use for review and push, ship with review. NOT for review only (review).
argument-hint: "[--gate-only] [--no-fix] [--no-audit] [--base=REV] [--repo=DIR] [commit message]"
allowed-tools: Bash, Read, Edit, Grep, Glob, Skill, Write, AskUserQuestion, Agent(general-purpose)
---

# Review and Push

## Goal

Gate a change, fix what the gate and the review confirm within fixed bounds, show the user everything
the loop changed, then commit and push exactly the approved tree, ending with a stable `Gate:` line.

## When NOT to use this skill

- **Just need to stage and commit**, no gate: use `commit-changes`; it is faster and does not block
  on quality checks.
- **Landing work on main and cleaning up branches and worktrees**: use `merge-and-cleanup`; this
  skill only commits and pushes the current branch.
- **A review with no gate, fix or commit**: use `review`.

## Terms

- gate - one of lint, tests, coverage. A **gate run** is one pass over the current tree; its states
  are `passed`, `failed`, `unavailable`, `not-applicable` and `excepted` (`references/fix-loop.md` §2).
- tripwire, pointer - the deterministic detections and ranked facts `diff-metrics` produces
  (`review`'s `references/metrics.md`).
- gate fix round - a fix of a failed lint or test gate; at most 3 per run.
- fix round, verify round - the single fix of confirmed findings the user selected, and the single
  check of it by an independent verifier.
- floor - the lowest severity the fix round fixes, asked of the user with `AskUserQuestion`.
- commit set - the paths the gate verified as one task; `commit-changes` commits exactly those.
- BASE - the revision the gate measures from: `--base=REV`, default HEAD.
- T0, T_gates, T_comments, T_review, T1, T2, T_final, T_end - tree snapshots of the working state
  (`references/fix-loop.md` §1).
- no user present - `AskUserQuestion` is unavailable or errors: every subagent, a headless run, a
  harness without it.

## Arguments

Leading tokens that start with `--` are flags; the rest is the commit message (a commit message never
starts with `--`). An unknown flag gets the grammar in one line and a question.

- `--gate-only` stops before the commit and push. `wrap-up` and `merge-and-cleanup` use it.
- `--no-fix` makes the gate write nothing: no gate fix rounds, no fix round, and a report-only
  comment pass. The `reviewer` agent and `orchestrate` pass it, because their retry loops own fixing
  and a tree edited with no user present could never be approved.
- `--no-audit` passes the token `no-audit` to `review`. Without it the cross-harness audit runs
  whenever an auditor is available, and `wrap-up` and `merge-and-cleanup` inherit that default.
- `--base=REV` gates everything since REV, committed or not.
- `--repo=DIR` gates the repository at DIR instead of the current directory's. Every gate command
  carries `--repo DIR` or `git -C DIR`, or runs as `cd DIR && ...` inside one Bash call; `review` gets
  `repo=DIR` and `commit-changes` works in `repo=DIR` (`wrap-up` passes it for each tree).

## Workflow

Load `references/fix-loop.md` first: it holds the run state, the gate run, the fixer rules and every
template named below.

1. **Start.** Snapshot T0, write ALL_DIRTY with `diff-metrics dirty`, record the base tree. A snapshot
   refusal (unborn HEAD, unmerged paths) is `BLOCKED`. When T0's tree equals the base tree there is
   nothing to gate: end at once with `Gate: PASSED`, commit set `(none)` and
   `Committed: not committed (nothing to gate)`. If the `last-pass` file for this repo matches (same
   repo, base tree and requested audit policy, and T0 equals its stored `t_end`), print the earlier
   final block marked `(reused)`, skip the commit set and the run record, and go to the commit of
   step 9 (`--gate-only`: end there).
2. **Gate phase.** Do a gate run. `unavailable` anywhere is `BLOCKED`. Lint or tests `failed`: up to 3
   gate fix rounds (none under `--no-fix`), each a snapshot, an inline fix under the fixer rules, a new
   gate run and the delta tripwires. Still failed is `BLOCKED`, before any review tokens are spent.
   Coverage `failed` goes to the coverage question: Continue makes coverage `excepted` with the
   approved lines recorded and sends the gaps to the Tests lens through `metrics.json`; Stop, or no
   user, is `BLOCKED`. Coverage never gets a fix round. Coverage `not-applicable` (no tool) does not
   block and prints as `unmeasured: coverage (no tool)`. Snapshot T_gates once, here.
3. **Comment pass** on added lines only (`fix-loop.md` §8). If it edited anything: snapshot
   T_comments, list the edits, run the delta tripwires on T_gates..T_comments, then a gate run on the
   edited tree with the rules of step 2 (the gate fix rounds left are shared with step 2). Snapshot
   T_review after it. With no edit, T_comments and T_review equal T_gates. Under `--no-fix` it only
   records candidates.
4. **Review.** Confirm the latest gate run is fresh. Write `<scratchpad>/review/claim.txt` with
   `diff-sha256: <sha256 of target.diff>` on line 1 and the session's task below it. Invoke the
   `review` skill with `since <BASE sha>` (and `repo=<DIR>` under `--repo`), no model token unless the user named one this session, and
   `no-audit` when `--no-audit` was given. No Verdict line, or a last line
   `review: evidence invalidated`, is `BLOCKED`. Otherwise act on the Verdict line and findings, and write
   the numbered confirmed findings to `RUN/round1.md`.
5. **Fix round**, once, only with confirmed findings and without `--no-fix`. Ask the floor question
   (`fix-loop.md` §5); with at least one finding selected: snapshot T1, fix inline, snapshot T2. Zero selected skips
   steps 5 and 6; say why.
6. **Verify round**, once, only after a fix round: a gate run on T2 (lint or tests not `passed` or
   `not-applicable` is `BLOCKED`; uncovered lines outside the exception ask the coverage question
   again, Stop or no user is `BLOCKED`), the T1..T2 tripwires, then the verifier agent. Unresolved
   findings, findings below the floor and regressions are "remaining".
7. **Decisions.** Under `--no-fix`, only report the entry the decision would add. Otherwise, when
   `docs/decisions.md` exists, append entries following its format. This is a loop change like any
   other: it joins the handoff and waits for the answer. Snapshot T_final after it.
8. **Handoff** when T_final differs from T0 (gate fixes, comment edits, the fix round or a decision
   entry) or anything remains (confirmed findings, comment candidates): the report, the full loop
   diff, then the question. Commit (Continue in `--gate-only`) gives `FIXED_APPROVED`; Stop, or no
   user, gives `FIXED_DECLINED` and the run goes to step 10 without committing. Otherwise the status
   is `PASSED` and no question is asked. After an approval, snapshot T_end; if it differs from
   T_final something changed after approval: `BLOCKED`. The gate runs stay those of T_review or T2:
   the decision entry touches only `docs/decisions.md`, and the final block prints it.
9. **Commit.** After `PASSED` or `FIXED_APPROVED`, in every mode: write the commit set file with
   `diff-metrics commit-set` and print its `Commit set:` line (skipped on a reused pass); then, unless
   `--gate-only`, commit and push through `commit-changes` (non-arc repos) with the commit message.
   `commit-changes` checks the staged tree against `tree=` before it commits and the commit's tree
   against it before it pushes. A Phabricator repo (an `.arcconfig` at the toplevel, or an origin on a gitolite or Phabricator host; `arc` on the PATH alone proves nothing) is gated but never published
   here: the diff tooling stages and rebases without an approved-tree check, so the run
   ends as `--gate-only` with `Committed: not committed (arc route: publish the diff
   yourself)`. `--gate-only` skips only the commit and push, because `wrap-up` and
   `merge-and-cleanup` commit from the file.
10. **Close.** Write the run record (not on a reused pass), the `last-pass` file after `PASSED` or
    `FIXED_APPROVED`, and the final block, with the Gate line last.

## The Gate line

`Gate: STATUS - fixed F, remaining R, unverified U, unmeasured: <checks>`. The prefix differs from
`review`'s `Verdict:` on purpose: callers grep it.

| Status | When |
|---|---|
| `BLOCKED` | a gate is `failed` after the gate fix rounds (at once with `--no-fix`), any gate is `unavailable`, coverage gaps with no approval to continue, the verify round's gate run is not green, or `review` ended without a Verdict line |
| `PASSED` | every gate `passed`, `not-applicable` or `excepted`, the loop changed nothing (T_final equals T0), `review` confirmed nothing, and no comment candidates remain; no handoff question |
| `FIXED_APPROVED` | the handoff ran and the user chose Commit (Continue in `--gate-only`) |
| `FIXED_DECLINED` | the handoff ran and the user chose Stop, or no user was present |

A `BLOCKED` run prints a `Blocked by:` line just before the Gate line, naming the gate and its state or
the reason, so callers can report it. Remaining (R) counts unresolved confirmed findings, confirmed findings below the floor, verify-round
regressions and, under `--no-fix`, comment candidates. `not-applicable` and unmeasured checks follow
`unmeasured:`. Example:
`Gate: FIXED_APPROVED - fixed 2, remaining 1, unverified 0, unmeasured: coverage (not applicable), complexity (.nix .sh)`.

## Key behaviors

**No AI attribution of any kind**
- Never add `Co-Authored-By`, `AI-Assistant:` or any other AI trailer or metadata.
- The human who commits is the sole author.
- Use plain ASCII in all commit and diff messages (no em dashes, smart quotes, unicode).

**The commit set decides what is committed**
- The gate verified the whole task while the loop edits only some files, so committing only the
  session's files would strand the rest. The commit set is the paths dirty at T0 plus every path the
  loop changed, and the tree check makes the commit exactly what was approved.

**Evidence is never carried across a change of tree**
- After gate fixes, comment edits and the fix round, a new gate run on the new tree.

**The loop never reverts and never hides**
- A tripwire on the loop's own changes is listed at the handoff, not reverted: replacing a bad test
  legitimately deletes assertions.
- Every loop change, comment edits included, waits for the handoff answer.

**Capture decisions when they exist**
- Record decisions only if `docs/decisions.md` exists, in its own format, in the same commit.

**Why `disable-model-invocation` stays off**
- This skill commits, but the `reviewer` agent invokes it through the Skill tool. The handoff is the
  user's control point.

## Error cases

| Situation | Action |
|---|---|
| Snapshot refused (unborn HEAD, unmerged paths) | `BLOCKED` with the message |
| A gate is `unavailable` | `BLOCKED`; name the command and why it could not establish anything |
| Lint or tests still failed after 3 gate fix rounds | `BLOCKED` before review |
| A tripwire in a loop delta | List it at the handoff; do not revert |
| Coverage gaps | The coverage question; Stop or no user is `BLOCKED` |
| No user present | No questions: `FIXED_DECLINED` when a handoff was due, nothing committed |
| No gate command found | The gate is `not-applicable`, printed after `unmeasured:` |
| Mutation unmeasured or partial | Carry `review`'s header line into the report |
| `review` ended without a Verdict line, or with `review: evidence invalidated` | `BLOCKED` ("review did not run" or "evidence invalidated") |
| Stale handed-in `metrics.json` or `claim.txt` | Re-run `measure`, rewrite the claim |
| `diff-metrics` not on PATH | Run `python3 -I ~/.config/ai/common/skills/review/scripts/diff_metrics.py` |
| The verifier fails | Its findings stay "unverified"; no second try |
| Something changed after approval (step 8) | `BLOCKED` |
| A hook changed the commit's tree | `commit-changes` stops before the push; a new gate is needed |
| `commit-changes` refuses a tree mismatch | Show its diff stat; commit nothing |
| The commit or push fails | `Committed:` says so; the Gate status stays |
| `docs/decisions.md` exists but its format is unclear | Stop; show it and ask |
| No library source covers this project | `review` runs ungrounded and labels it; carry that label into the report |

## Hard prohibitions

Never:
- Treat an `unavailable` or unmeasured gate as passed.
- Commit while confirmed findings remain without the user's commit answer.
- Skip the comment pass or leave obvious noise comments.
- Force-pass lint or tests with flags or workarounds.
- Use `Co-Authored-By` or any AI trailer or metadata on commits or diffs.
- Use unicode punctuation (em dashes, smart quotes) in commit or diff messages.
- Commit without passing all quality gates.
- Hand the fixer a metric value.
- Fix a failing test by editing its expectation without a confirmed finding saying the test is wrong.
- Auto-revert a fix that trips a tripwire.
- Commit any loop change, comment edits included, without the handoff answer.
- Rely on gate evidence from an earlier tree.
