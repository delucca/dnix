---
name: wrap-up
description: Closes a session end to end. Lands or pushes the checkout, removes the task worktree, then records what was learned through note. Manual only. NOT for landing alone (merge-and-cleanup).
argument-hint: "[target branch (default: main)]"
allowed-tools: Bash(git:*), Skill, Read, AskUserQuestion
disable-model-invocation: true
---

# Wrap Up

Close out a work session in one pass: get the work off this machine (landed on the target branch when the repo is yours, pushed to its remote when it is not), remove the task worktree, and record what the session decided or learned through `bilbo:note`.

## When NOT to use this skill

- **Landing on main without recording anything** -- use `merge-and-cleanup`.
- **Committing only**, no landing, no cleanup -- use `commit-changes`.
- **Recording knowledge with no code to land** -- use `bilbo:note` directly.
- **Gate, fix, commit and push** without landing or a note -- use `review-and-push`; this skill runs its gate itself, in gate-only mode.
- **Opening the review itself** -- opening a review, e.g. `open-pull-request`, is a deliberate step; this skill publishes the branch, it does not request review.

## What this skill owns

Three skills and plain git do the work. This one classifies the checkout, sequences them, and carries the session's evidence across the boundaries between them.

| Phase | Delegate | Why |
|---|---|---|
| Classify | this skill | The path splits on one fact only the checkout can answer: its origin |
| Gate | `review-and-push --gate-only` | Runs before the brief (Phase 0b), so the brief records what the gate fixed and decided |
| Land (own repo) | `merge-and-cleanup` | It already runs `commit-changes` as its own Phase 1 and removes the worktree in its Phase 3 |
| Publish (any other repo) | `commit-changes` with push | The branch must reach a remote, and nothing else: landing someone else's main is not this session's call |
| Clean | `git worktree remove` | Removes the task tree once its branch is committed and either landed or published |
| Note | `bilbo:note` | Runs last so the note cites the SHA that landed or the ref that was published |

Delegate, never reimplement: raw `git add`/`git commit`/`git rebase` bypasses the safe-staging rules in `commit-changes`, and a note written by hand bypasses `bilbo:note`'s same-topic check and frontmatter.

**Target branch**: `$0` -- the first argument -- when it names a branch that exists locally or on origin, otherwise `main`. Call it **TARGET**. (`$0` is the first argument and `$1` the second, so a skill reaching for `$1` here would silently read nothing and fall back to `main`.) When `$ARGUMENTS` holds anything that is not that branch name, treat it as note guidance -- the user's steer on what is worth recording.

## Phase 0 -- Preflight and classification

Confirm the delegates appear in the available-skills list.

- `merge-and-cleanup` or `commit-changes` missing -> stop, and tell the user they are not installed.

Then classify every tree this session worked in. Each answer below is read from the checkout itself, never from the machine's name.

1. **The tree.** Resolve the checkout from the session's own working tree, never by building a path out of the repo's name.

   ```bash
   git rev-parse --show-toplevel   # the tree this session is in
   git worktree list --porcelain   # first entry is the main checkout
   ```

   Call that first entry **CHECKOUT**. Every entry after it is a linked worktree, which can live anywhere; `merge-and-cleanup` handles them all. The session worked in CHECKOUT, or in one such linked worktree. More than one repo touched -> one pass each.
2. **Ownership**, from the origin URL:

   ```bash
   git -C <tree> remote get-url origin
   ```

   `ownRemotes` in `~/.config/ai/settings/wrap-up.json` is a list of regexes. A URL matching any of them -> **OWN**: land on TARGET. Anything else (another org, a fork's upstream) -> **OTHER**: publish only. A missing file or an empty list means everything is OTHER.

Print the classification in one line before anything irreversible runs, e.g. `repo.task: OWN (matches ownRemotes) -> land on main` or `repo.task: OTHER (no ownRemotes match) -> publish only`.

## Phase 0b -- Gate

Per tree that has work pending:

1. Resolve `default`, the first that works: `git -C <tree> symbolic-ref --short refs/remotes/origin/HEAD`; `origin/TARGET` when `git -C <tree> rev-parse --verify --quiet origin/TARGET` succeeds (origin exists but its HEAD ref was never set); the branch `git -C <tree> remote show origin` names as HEAD branch, prefixed with `origin/`; TARGET when there is no origin. It is remote-tracking, so unpushed commits on main count. Then `base` is the output of `git -C <tree> merge-base "$default" HEAD`. Never use `<upstream>..HEAD`: a new branch has no upstream.
2. Nothing pending (`git -C <tree> status --porcelain=v1` is empty and `git -C <tree> log --oneline "$base"..HEAD` is empty): record `Gated: skipped, nothing pending` and go on.
3. Otherwise invoke `review-and-push` with `--gate-only --base=<base> --repo=<tree>`, so the gate runs in that tree and not in the session's current directory. It reuses an earlier pass on exactly the same trees itself.
4. `PASSED` or `FIXED_APPROVED`: continue to Phase 1. `FIXED_DECLINED` or `BLOCKED`: stop, and report the Gate report and "Left undone".
5. The commit still happens in `merge-and-cleanup` or `commit-changes`, which take the gate's `Commit set:` line for this repo and check the staged tree against it, so the OWN prohibition and the no-review-request rule both hold. A rebase in `merge-and-cleanup` that changes content is re-gated there before any push.

## Phase 1 -- Draft the note brief

Write the brief now, while the work still exists on disk. Phase 3 deletes the worktree holding it, and a brief reconstructed afterwards has lost the diff it came from.

Read back over the session and collect:

- **Decisions** -- what was chosen and what was rejected, with the reason. A decision recorded without its alternative is not worth a note.
- **Gotchas** -- anything that cost time and would cost it again: a tool that reported something untrue, a flag that behaved unexpectedly, an assumption that failed.
- **State changes** -- what now exists or is now true that was not before: a service provisioned, a file retired, a version shipped.
- **Evidence** -- the branch name, the files touched, and any verification actually run (not verification that was merely planned).

A handful of bullets is the right size. `bilbo:note` owns the note prose, the kind, the scope and the same-topic check.

If nothing durable surfaced -- a typo fix, a rerun, a question answered from context -- record that the brief is empty and carry that into the report. Inventing material so `bilbo:note` has something to do pollutes the notes, which is worse than a quiet session.

## Phase 2 -- Land (OWN) or publish (OTHER)

### 2a -- OWN: land on TARGET

Invoke `merge-and-cleanup` with TARGET as its argument.

It is a gated pipeline in its own right: it stops on a rebase conflict, a rejected push, a dirty checkout, or an unmerged branch that needs approval. When it stops, stop here too -- and print the Phase 1 brief in the report, so the session's findings survive a run that did not finish.

Its Phase 3 removes any linked worktree cut for the task, so Phase 3 below only verifies. Continue only once it reports the landing verified, and record the landed SHA:

```bash
git -C <CHECKOUT> log -1 --format='%h %s' origin/TARGET
```

This is what makes the note citable months later -- existing notes carry lines like `shipped as dnix 76c157f`, and a branch name deleted in Phase 3 resolves to nothing.

### 2b -- OTHER: publish the branch

Invoke `commit-changes` with push enabled. If it reports nothing to commit, continue -- the work may have been committed earlier in the session. Before any raw `git push` below, run `git -C <tree> rev-parse HEAD^{tree}`: with a `Commit set:` line for this repo it must equal that `tree=`, otherwise stop and require a new gate.

Then check the publish bar: every commit on the branch is held by a remote.

```bash
git branch -r --contains HEAD          # non-empty: already published
git push -u origin HEAD                # otherwise
```

- Push refused, and every commit in `git log origin/main..HEAD` carries one of the trailers named in `publishedTrailers` (a list such as `["Differential Revision:"]` in `~/.config/ai/settings/wrap-up.json`) -> published: the review tool that amended that trailer into the commit holds the patch. A missing or empty list means no trailer exception.
- Push refused and no such trailer -> stop and ask. The branch exists nowhere but this checkout, and Phase 3 would delete any linked worktree holding it.

No rebase, no fast-forward of TARGET, no remote branch deletion: on a repo that is not yours, landing belongs to its review flow (Submit Queue, a merged PR), and the pushed branch is what that flow reads.

Record the published ref now, before Phase 3 removes any linked worktree that holds it: the branch name and its tip SHA (`git rev-parse --short HEAD`), plus any `D<digits>` revision or PR number the session produced.

## Phase 3 -- Clean the tree

Remove a tree with `git -C <CHECKOUT> worktree remove <path>` and use only `git -C <CHECKOUT> ...` afterwards: the shell's working directory dies with a removed tree, and `cd` is outside this skill's `Bash(git:*)`.

- **OWN** -- `merge-and-cleanup` already removed any linked worktree cut for the task. Verify with `git -C <CHECKOUT> worktree list --porcelain`: only the checkout remains. The checkout itself is never removed; if the session worked there directly, the report says `nothing removed: worked in the checkout` rather than treating it as kept.
- **OTHER** -- if the session worked in a linked worktree, `git worktree remove` it, then `git -C <CHECKOUT> branch -d <name>`, the name taken from the `branch refs/heads/<name>` line `git worktree list --porcelain` gave for that worktree, now that a remote holds it (the remote branch stays: it is the published work). If the session worked directly in the checkout, nothing is removed.
- **`git worktree remove` refuses "not clean"** -- something was not committed; go back to Phase 2, never `--force`.
- **Forcing** -- `git worktree remove --force` only after the user approves that specific tree, with the blocker named.

## Phase 4 -- Note

Invoke `bilbo:note`, handing it the Phase 1 brief plus:

- the repo name and the ref from Phase 2: the landed short SHA on TARGET, or the published branch, tip SHA, and revision or PR ids
- the date in absolute form, never "today" or "last week" -- the note is read long after this session
- any note guidance the user passed in `$ARGUMENTS`

`bilbo:note` owns the kind, the scope, the same-topic check and supersession. Naming a kind or a file here preempts judgment it makes better with the store's notes in front of it.

Skip this phase only when the Phase 1 brief is empty.

## Phase 5 -- Report

One block, no preamble:

- **Gated** -- the Gate line, or `skipped: nothing pending`
- **Landed** or **Published** -- the commit subjects now on TARGET with the short SHA, or the branch, tip SHA and revision/PR ids that were pushed
- **Cleaned** -- any linked worktree removed and its branch dropped, plus anything kept and why; `nothing removed: worked in the checkout` when the session ran directly in CHECKOUT
- **Noted** -- the note path, whether it was created or updated, and its scope, or `skipped: nothing durable surfaced`
- **Left undone** -- anything a phase stopped on, named plainly rather than folded into a success line

## Troubleshooting

| Symptom | Cause | Resolution |
|---|---|---|
| `merge-and-cleanup` stops on a rebase conflict | TARGET moved under the branch, or the branch diverged | Resolve it with the user, then rerun `/wrap-up`; the Phase 1 brief still stands |
| `git push` refused on an OTHER repo | The remote takes no branches, or the branch is protected | Phase 2b: a `publishedTrailers` trailer on every commit means it is published; otherwise ask before anything is deleted |
| `git worktree remove` dies "not clean" | Uncommitted work in the worktree | Back to Phase 2; `--force` discards it |
| Shell commands fail with "no such directory" after Phase 3 | The removal ran from inside the tree | Use `git -C <CHECKOUT> ...` forms; the removal itself succeeded |
| `bilbo:note` asks which scope the note belongs to | The note came out unassigned, or its scope looks wrong for the subject | Answer with one of the scopes it names |
| The gate stops (`BLOCKED`, `FIXED_DECLINED`) | A gate failed or was unavailable, or the user declined the loop's changes | Fix or decide, then rerun `/wrap-up`; an unchanged tree reuses the pass |
| Nothing to commit but the branch remains | The work was pushed in an earlier session | Expected; Phase 2 continues to the publish bar or the landing |

## Hard prohibitions

- Never reimplement a delegate. The staging rules in `commit-changes`, the approval gates in `merge-and-cleanup`, and `bilbo:note`'s same-topic check all exist because bypassing them loses work quietly rather than loudly.
- Never invoke `commit-changes` on the OWN path. `merge-and-cleanup` already does, and a second pass restages what the first one handled.
- Never land a repo that is not OWN. Rebasing, fast-forwarding TARGET, or deleting remote branches on someone else's repo is not this session's call, however clean the branch looks.
- Never `git worktree remove --force` past an unpublished branch. It is the only copy of someone's work until proven otherwise.
- Never remove CHECKOUT, the first entry of `git worktree list`. It is where TARGET lives, not a task worktree.
- Never write a note with `Write` or `Edit`. Every note goes through `bilbo:note`.
- Never enter Phase 4 with the landing or the publish bar unverified. A note citing a SHA that never reached a remote is worse than no note, because it reads as true.
- Never land or publish past a `BLOCKED` or `FIXED_DECLINED` gate.
- Never skip `bilbo:note` to finish sooner. An empty brief is a reason; time pressure is not.
