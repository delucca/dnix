# The gate and fix loop

Loaded at step 1 of `review-and-push`. This file holds the mechanics: run state, the gate run, the
fixer's rules, the question and report templates, the comment pass, the commit set, the final block,
the run record and the reuse rule.

Contents: 1 run state; 2 gate run; 3 fixer rules; 4 tripwires on loop deltas; 5 floor question; 6
verifier prompt; 7 handoff report; 8 comment pass; 9 commit set; 10 final block; 11 run record; 12
reuse.

## 1. Run state

`RUN` is `<scratchpad>/review-gate/<run_id>/`, with `run_id` the output of `date -u +%Y%m%dT%H%M%SZ`
plus the short id of T0.

Every snapshot is `diff-metrics snapshot --repo <toplevel> --index-dir RUN/index`. The verb scopes
`GIT_INDEX_FILE` per git call itself, so the prefix trap of a shell `&&` chain cannot happen, and it
refuses an unborn HEAD or unmerged paths: that refusal is `BLOCKED`, with its message.

| Snapshot | When |
|---|---|
| T0 | at the start |
| T_gates | after the gate phase; equal to T0 when no gate fix ran |
| T_comments | after the comment pass; equal to T_gates when it edited nothing |
| T_review | the tree `review` sees: the last gate run's tree; it differs from T_comments only when the gate re-run after the comment pass needed a fix round |
| T1, T2 | around the fix round; T1 equals T_review |
| T_final | the last of these |
| T_end | after the decisions step |

ALL_DIRTY at T0 is written by `diff-metrics dirty --repo <toplevel> --out RUN/dirty`: every dirty path,
renames reported as a deletion plus an addition so both paths appear. The base tree is
`git rev-parse <BASE>^{tree}`.

## 2. Gate run

A gate run covers the current tree. `k` counts the runs.

1. `tree_k` is a new snapshot.
2. `diff-metrics diff --repo <toplevel> --base <BASE> --worktree > <scratchpad>/review/target.diff`, then
   `diff-metrics measure --repo <toplevel> --diff <scratchpad>/review/target.diff --out <scratchpad>/review/metrics.json --base <BASE> --worktree`.
   Lint, test and coverage commands below run in `<toplevel>`.
3. Lint. Find the command in the repo's AGENTS.md or CLAUDE.md, then justfile or Makefile targets
   `lint` and `check`, then manifests (`package.json` scripts, `pyproject.toml`, `Cargo.toml`,
   `go.mod`). Ask for line-oriented output (`eslint -f unix`, `ruff check --output-format concise`,
   `golangci-lint run --out-format line-number`, `cargo clippy --message-format short`,
   `shellcheck -f gcc`). Record the exit code and pipe the output through
   `diff-metrics filter-lint --metrics <scratchpad>/review/metrics.json`. Classify with the states
   below from the tool's documented exit codes and the `kept=K located=M unlocated=N` line.
4. Tests: the test command. Exit 0 is `passed`, a test failure is `failed`, a command that cannot
   start or a tool-error exit is `unavailable`.
5. Coverage: the stack's report as lcov or a Go profile, with every artifact written under `RUN/` and
   none in the worktree (`COVERAGE_FILE=RUN/.coverage-k pytest --cov --cov-report=lcov:RUN/coverage-k.info`,
   `vitest run --coverage --coverage.reportsDirectory=RUN/cov-k --coverage.reporter=lcov`,
   `cargo llvm-cov --lcov --output-path RUN/coverage-k.info`, `go test -coverprofile=RUN/coverage-k.out ./...`).
   A tool that cannot write elsewhere gets its artifacts removed afterwards. Then
   `diff-metrics measure ... --coverage <that file> --coverage-langs <the languages the coverage tool covers, comma separated> --out <scratchpad>/review/metrics.json` over the
   same `target.diff`, so line numbers match the tree that produced the report, and write two lines to
   `<scratchpad>/review/coverage.path`: the report's path and `diff-sha256: <hash of that target.diff>`,
   so `review` passes it again only while the diff is the same. Delete `coverage.path` when coverage
   is `not-applicable`.
   `checks.uncovered` measured with an empty `pointers.uncovered` is `passed`. A check that
   `measure` reports as unmeasured (a report with no line data, or one for other file types than the
   changed files) is `unavailable`, never `passed`.

   Before running a coverage command, check that the repo's coverage tool covers a language in
   `facts.languages` that is not Nix, shell, Make, Docker, SQL, Markdown or a config format (shell
   counts when the tool reports it). Otherwise coverage is `not-applicable` (printed as `unmeasured:
   coverage (no tool for <languages>)`) and no command runs. After `measure`, read
   `checks.uncovered`: `applicable: false` is `not-applicable`; `unmeasured` with `applicable: true` is
   `unavailable`; in a mixed change `checks.uncovered.languages` holds each language's status, and a
   covered language without evidence is `unavailable` even when another language is measured. Pass
   `--coverage-langs` with the languages the repo's coverage tool covers, named as in `facts.languages`
   (`python`, `typescript`; an unknown name such as `py` is refused with exit 2): a changed language outside that
   list reads `outside tool scope` and is reported without blocking, while the uncovered lines of the
   measured languages stay in `pointers.uncovered` either way.
6. Write `RUN/gate-run-k.json`: `tree`, `lint`, `tests`, `coverage` (state and detail), the lint
   exit code and `coverage_sha256`.

| State | Meaning |
|---|---|
| `passed` | the command ran and established success: tests exited 0; lint exited with a code its tool documents as success or issues-found, `filter-lint` kept no line, and when the exit code says issues were found it located at least one line (else the output was not understood: `unavailable`); coverage produced a report `measure` read, with no uncovered changed line |
| `failed` | the command ran and found a problem on this change: tests failed, `filter-lint` kept a line, or changed lines are uncovered (coverage then goes to the coverage question, never to a fix round) |
| `unavailable` | a command exists but could not establish anything: missing binary, crash, a tool-error exit, output not understood, a coverage report `measure` could not read |
| `not-applicable` | the repo has no such command for the changed languages; printed after `unmeasured:` |
| `excepted` | coverage only: uncovered lines the user approved, recorded by file and stripped line text (numbers shift when an edit moves them); a later run whose uncovered lines are all among them stays `excepted`, any new one asks again |

Read each tool's documented exit codes before classifying (eslint 0/1/2, ruff 0/1/2, shellcheck
0/1/2-4) and record them in the run. The latest gate run is **fresh** only while a new snapshot
equals its `tree`. Steps 4, 6 and 8 of the skill check freshness before relying on it.

## 3. Fixer rules

The fixer works inline in this session, so `commit-changes` sees its edits. Each rule has a reason.

- Never see a metric value. An automated Extract Method cleared 78% of Sonar's cognitive-complexity
  warnings: a number handed to a fixer gets met, not fixed.
- Never fix a failing test by editing its expectation unless a confirmed finding says the test is
  wrong. The cheapest way to pass `assertEqual(x, 3)` is to write 4, and no tripwire sees it.
- No suppressions, skips, coverage pragmas or config loosening.
- No extract-method or split refactors for complexity.
- Touch only files in the diff and their tests.
- Never write a test only to reach the coverage number: a test that asserts nothing covers lines.

## 4. Tripwires on every loop delta

For each pair of consecutive snapshots the loop produced by editing (gate fix rounds, the comment
pass, the fix round):

```bash
diff-metrics diff --repo <toplevel> --base <A> --head <B> > RUN/delta-<A>-<B>.diff
diff-metrics measure --diff RUN/delta-<A>-<B>.diff --out RUN/delta-<A>-<B>.json --base <A> --head <B>
diff-metrics bundle --metrics RUN/delta-<A>-<B>.json --diff RUN/delta-<A>-<B>.diff --dir RUN/delta-<A>-<B>/
```

Each `tripwires.md` there is listed at the handoff and never reverted: replacing a bad test
legitimately deletes assertions. The fix round's pair (T1, T2) feeds the verifier as
`delta-T1-T2.diff` and `delta-T1-T2/tripwires.md`.

## 5. The floor question

Print the numbered confirmed findings, then ask with `AskUserQuestion` (single select): "Review
confirmed N findings (a critical, b major, c minor, d nit). Which should the fix round fix?", header
"Fix floor", options "Critical and major", "Minor and up", "Everything, nits too", "None, hand off
as is". The automatic Other field takes finding numbers such as `1, 3, 7`. A finding marked
`audit: disputed by <auditor>` keeps its mark in the list. Unverified findings are never fixed. Zero
selected (by the answer, an empty floor, or no user) skips the fix and verify rounds.

## 6. The verifier prompt

One agent spawned the way `review` Step 1 spawns its lenses (its per-harness table: `Agent` with
`general-purpose` on Claude Code, `spawn_agent` or `cross-audit spawn` on Codex, `invoke_subagent` on
agy) on the model `review` uses by default for the harness, or the user's `verify=` token, filled
with absolute paths:

```
You are the verify round of a fix loop. Another session fixed code; you check its work.

Round-1 confirmed findings, numbered: <ABS>/review-gate/<run_id>/round1.md
Selected for fixing: <numbers>
The fixer's changes (git diff T1 T2): <ABS>/review-gate/<run_id>/delta-T1-T2.diff
Tripwires on those changes: <ABS>/review-gate/<run_id>/delta-T1-T2/tripwires.md
Repository root; the final tree is its working tree: <ABS repo>

Part 1. For every round-1 finding, selected or not, re-read its location in the final tree and answer:
    <n>. RESOLVED - <the final code that settles it, quoted>
    <n>. UNRESOLVED - <why it still holds, quoting the final code>
    <n>. UNVERIFIABLE - <what it would take>
Assume each finding is unresolved and mark RESOLVED only on concrete evidence. A fix that hides the symptom (a suppression, a skipped test, an edited expectation with no finding calling the test wrong) is UNRESOLVED.

Part 2. Regressions: defects the fixer's changes introduced, at most 10, each located on a line of the fixer's diff, in this shape:
    [SEVERITY] path:LINE — one-sentence claim
    evidence: `<exact quote>`
    grounding: code: <path>:<line> | judgment
    confidence: high | medium | low

Read-only: no edits, commits or posts, and do not run the project's code; the gates already ran on this tree.
```

## 7. Handoff report

It leads with what was not verified:

```
## Gate report: <repo> since <base short> (<N> files)

Not verified: unmeasured or not applicable <checks and languages>; <U> unverified findings; tests the loop wrote: <paths | none>; tripwires on the loop's own changes: <list | none>
Gate fixes (T0..T_gates, plus T_comments..T_review when the re-run fixed anything): git diff --no-ext-diff --stat per pair, or none
Comment pass (T_gates..T_comments): <n> removed, <m> rewritten, in <files>, or none (under --no-fix: the candidates, unedited)
Fix round (T1..T2): git diff --no-ext-diff --stat <T1> <T2>, or skipped (<why>)
Decision entry: <the entry for docs/decisions.md | none> (under --no-fix: the entry it would add, unwritten)
Fixed: <list>
Remaining: <unresolved, below the floor, regressions, comment candidates>
Unverified: <list>
Gates on <T_final short>: lint <state>, tests <state>, coverage <state>, <k> gate fix rounds; mutation: <status>
```

Then the full loop diff (`git diff --no-ext-diff <T0> <T_final>`), then the question: "Commit these
changes?" with "Commit" and "Stop" (`--gate-only`: "Continue" and "Stop").

The coverage question, when changed lines are uncovered and the user is present: "N changed lines
are uncovered. Continue with the gaps (they go to the Tests lens), or stop?" with "Continue" and
"Stop". An approval covers the gaps it saw; a later gate run with more uncovered lines asks again.

## 8. The comment pass

Candidates are `pointers.comments` from the fresh `metrics.json`, plus trailing comments and
docstrings found by reading the added lines of `target.diff` (the script does not detect those).

Keep-list: license headers, tool directives (anything marked `directive`), doc comments the project
requires (a lint rule or the repo's rules say so), comments stating a non-obvious why or a trap. The
repo's AGENTS.md or CLAUDE.md comment rule wins.

Survivors go through an installed text-humanizing skill, if one is listed. Collect them with `file:line` into `RUN/comments.md`,
invoke the skill on that file, then apply its rewrites with Edit, keeping identifiers, markers
(`TODO(owner)`, `SAFETY:`) and required syntax untouched. Under `--no-fix` nothing is edited: the
removals and rewrites it would make are listed as comment candidates.

## 9. The commit set

Written only after `PASSED` or `FIXED_APPROVED`, in `--gate-only` runs too:

```bash
diff-metrics commit-set --repo <toplevel> --from <T0> --to <T_end> --dirty RUN/dirty --out RUN/commit-set
```

The file is the union of the paths changed between T0 and T_end (rename detection off, so both sides
of a rename appear) and ALL_DIRTY, NUL separated, sorted, deduplicated, without any path that is in
neither the worktree (a broken symlink counts as present) nor the index: such a path is a deletion
already staged, and naming it would abort the staging. `commit-changes` stages from the toplevel with
`git add -A --literal-pathspecs`. The file is bound to the repo and the tree, so the line is one of:

```
Commit set: repo=<abs toplevel> tree=<T_end> paths=<n> file=<abs path of commit-set>
Commit set: repo=<abs toplevel> tree=<T_end> (none)
Commit set: repo=<abs toplevel> (not approved: <STATUS>)
```

Print it before committing and again in the final block.

## 10. The final block

The last lines of every run, `BLOCKED` included:

```
Gated tree: repo=<abs toplevel> tree=<T_end, or the last snapshot when blocked earlier> base=<BASE sha>
Exceptions: coverage, <n> changed lines uncovered, approved | none
Commit set: <one of the three forms>
Committed: <sha> pushed | <sha> not pushed (<error>) | not committed (<--gate-only | FIXED_DECLINED | BLOCKED | commit failed: <error>>)
Blocked by: <gate and state, or the reason>            (only when BLOCKED)
Gate: <STATUS> - fixed F, remaining R, unverified U, unmeasured: <checks>
```

A failed commit or push leaves the Gate status as it was and says so on the `Committed:` line; the
run record gets `commit_error`.

## 11. The run record

Append one JSON line to `~/.local/state/review-gate/runs.jsonl` in every run that got past argument
parsing. `mkdir -p` the folder, write the record to `RUN/record.json` with Write, then:

```bash
python3 -I -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])), sort_keys=True))' RUN/record.json >> ~/.local/state/review-gate/runs.jsonl
```

Fields: `run_id`, `repo`, `origin`, `base`, `t0`, `t_gates`, `t_comments`, `t_review`, `t1`, `t2`,
`t_final`, `t_end`, `committed` (SHA or null), `commit_error`, `flags`, `gate_runs` (the
`gate-run-k.json` contents), `mutation`, `floor`, `findings` (`id`, `source`, `severity`, `verdict`,
`selected`, `resolved`), `tripwires_fired`, `loop_tripwires`, `comment_edits`, `coverage_exception`,
`audit` (the requested policy and each auditor's status), `unmeasured`, `handoff` (`commit`, `stop`,
`none`, `no-user`), `status`, `patch`.

When the loop changed anything, also write
`diff-metrics diff --repo <toplevel> --base <T0> --head <T_final> --binary > ~/.local/state/review-gate/<run_id>.patch`: git
prunes the unreachable snapshot trees after about two weeks, right at the 14-day rework window.
Later matching uses `git patch-id` or content, never SHAs (squash merges rewrite them). Version 1
keeps records only; nothing analyses them.

## 12. Reuse

After `PASSED` or `FIXED_APPROVED`, write
`<scratchpad>/review-gate/last-pass/<first 12 hex of sha256(toplevel)>.json` with `repo`, `base`
(SHA), `base_tree`, `t_end`, `status`, `run_dir`, `audit` (the requested policy: `on`, or `off` from
`--no-audit` or `REVIEW_CROSS_AUDIT=off`) and `coverage_exception` (the approved uncovered lines, or
null).

A later run in the same repo whose base tree and requested audit policy match, and whose current T0
equals the stored `t_end` (the tree the earlier run approved and left behind), prints the earlier
run's final block from `run_dir` (the Gated tree line, its `Commit set:` line, whose file is still
valid because the tree is the same, and the Gate line marked `(reused)`). It skips the commit set
writing and the run record, and goes straight to the commit and push, or ends in `--gate-only`. Any change of either tree means no reuse: a
content-changing rebase is re-gated in full. A pass made with the audit off never satisfies a run
that asks for it. A reused run writes no run record.
