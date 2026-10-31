---
name: merge-and-cleanup
description: Commits, rebases onto main, deletes merged branches and worktrees. Use for merge and cleanup, land this on main. NOT for committing only (commit-changes).
argument-hint: "[target branch (default: main)]"
allowed-tools: Bash(git:*), Skill, ExitWorktree, Read
---

# Merge & Cleanup

Land all current work on the target branch and leave the repo in its cleanest possible state: one checkout, one branch, everything pushed.

## When NOT to use this skill

- **Only need to commit** (no landing on main, no cleanup) — use `commit-changes` instead.
- **Need the quality gate before pushing** (test coverage, library-driven code review, lint/tests) — use `review-and-push` instead.
- **Opening a PR rather than merging directly** — use `open-pull-request` instead; this skill lands work on main, it does not create a pull request.
- **Closing out the whole session**, landing the work *and* recording what it decided or taught - use `wrap-up` instead; it calls this skill and then `bilbo:note`.

**Target branch**: `$1` if provided, otherwise `main`. If neither exists locally nor on origin, resolve the default branch from `origin/HEAD` (`git symbolic-ref refs/remotes/origin/HEAD`), use it, and mention the substitution in the final report. Call it **TARGET** below.

This skill is a pipeline — each phase gates the next. If a phase fails or needs user input, stop there; never skip ahead to cleanup with work not yet landed, because cleanup deletes the branches that still hold that work.

## Phase 0 — Preflight

Run in parallel:

- `git fetch --prune origin` — every later merged/unmerged judgment depends on fresh remote state
- `git worktree list --porcelain` — record the main checkout (first entry) and all linked worktrees after it. Read the checkout off this listing rather than building a path from the repo's name, which does not carry its group: it is the clone the repo was checked out to. Call it **CHECKOUT**. It is never a cleanup candidate
- `git status --porcelain=v1` and `git branch --show-current` — current state

Stop and ask the user before continuing if:

- HEAD is detached (no branch to land)
- There is no `origin` remote — offer to continue with local-only landing and cleanup
- An interrupted rebase/merge/cherry-pick is in progress (`git status` says so)
- The `commit-changes` skill is not in the available-skills list — tell the user to switch the host so it is linked; do not fall back to raw commits

## Phase 1 — Commit and push

Run every git command in this skill as `git -C <toplevel>`, the session's repo (the `repo=` of a `Commit set:` line when one was printed): the shell's directory does not persist between calls and `cd` is outside `Bash(git:*)`.

Invoke the `commit-changes` skill with push enabled. It owns the safe-staging rules (only session-touched files, atomic conventional commits) — do not reimplement or bypass it with raw `git add`/`git commit`.

If it reports nothing to commit, that is fine — continue; landing and cleanup are still wanted.

## Phase 2 — Land on TARGET

If the current branch already is TARGET: confirm it is pushed (`git status -sb` shows no `ahead`) and go to Phase 3.

Otherwise, from the work branch:

0. **Note where the branch stands.** Run `git rev-parse HEAD` and keep the SHA it prints; step 1b compares against it.
1. `git rebase origin/TARGET` (or local TARGET when there is no origin). Rebase-then-fast-forward keeps main's history linear, matching this repo's convention.
   - **On conflict**: stop. Show the conflicting files, and ask the user whether to resolve together or `git rebase --abort`. Never auto-resolve with `-X ours`/`-X theirs` — a silent wrong resolution lands directly on main.
1b. **Re-gate a rebase that changed content.** When this conversation printed a `Gated tree:` or `Commit set:` line whose `repo=` is this toplevel, run `git diff --no-ext-diff --quiet <the SHA from step 0> HEAD`. Exit 1 means the rebase brought upstream changes into the tree, so do not push yet: run `git merge-base origin/TARGET HEAD` (`TARGET` alone when step 1 rebased onto the local branch), then invoke `review-and-push` with `--gate-only --base=<the SHA it printed>`. `PASSED`: go to step 2. `FIXED_APPROVED`: the gate's edits are uncommitted, so invoke `commit-changes` (it takes the new commit set and checks the tree), then step 2. `FIXED_DECLINED` or `BLOCKED`: stop and report; the rebased branch stays local and TARGET is untouched. Why: the gate covered the branch before the rebase, and step 2 publishes the combined tree.
2. **Check the approved tree, then** fast-forward the remote. When this conversation printed a `Commit set:` or `Gated tree:` line with `tree=` for this repo, run `git rev-parse HEAD^{tree}`: after a rebase that changed content step 1b's new gate printed a new line, otherwise it must equal the latest `tree=`. Any other id (a hook, a skipped gate) means no push and a new gate; this holds when `commit-changes` found nothing to commit. Then: `git push origin HEAD:refs/heads/TARGET`. After a clean rebase this is a fast-forward; if it is rejected as non-fast-forward, someone pushed meanwhile — go back to step 1, do not force.
3. Update the local TARGET: if the main checkout is dirty, stop and ask — its changes are not this session's to discard. Otherwise `git -C <main-checkout> checkout TARGET` (if not already on it), then `git -C <main-checkout> merge --ff-only origin/TARGET`.

Verify before moving on: `git merge-base --is-ancestor <work-branch> origin/TARGET` succeeds. If it does not, the work is not landed — stop and report rather than continuing to a cleanup that would delete it.

## Phase 3 — Cleanup

Order matters: worktrees first (a branch checked out in a worktree cannot be deleted), then local branches, then remote.

### 3a — Worktrees

If the session is currently inside a worktree the harness cut (under `<tree>/.claude/worktrees/`), call `ExitWorktree` first — a worktree cannot be removed from within itself. Inside any other worktree, remove it with `git -C <CHECKOUT> worktree remove <path>` and run every later command in the `git -C <CHECKOUT> ...` form: the shell's working directory dies with the tree, and `cd` is outside this skill's `Bash(git:*)`.

For every linked worktree (all but CHECKOUT), whether it was cut by hand into `~/Developer/<group>/.worktrees/<repo>.<task>` or by the harness under `<tree>/.claude/worktrees/`:

- Clean (`git -C <path> status --porcelain` empty) **and** its branch is an ancestor of TARGET → `git worktree remove <path>`
- Dirty or holding an unmerged branch → add to the ASK list

Finish with `git worktree prune`.

### 3b — Local branches

List all local branches except TARGET. A branch removed with its worktree in 3a is simply absent.

- Merged (`git branch --merged TARGET`) → `git branch -d <name>`
- Unmerged → add to the ASK list

### 3c — Remote branches

Skip when there is no origin. List `git branch -r --merged origin/TARGET`, excluding `origin/TARGET` and `origin/HEAD`.

- Merged **and** yours (matches your branch prefix, or its name matched a local branch handled in 3b) → `git push origin --delete <name>`
- Merged but not recognizably yours, or unmerged → add to the ASK list. On a shared repo, someone else's branch is never yours to delete silently, even when merged.

### 3d — The ASK list

If the ASK list is non-empty, present it once — each item with its blocker (dirty worktree, N unmerged commits with a one-line `git log --oneline` sample, foreign remote branch) — and ask which to delete. Only after explicit approval use the forcing forms (`git branch -D`, `git worktree remove --force`, `git push origin --delete`). Anything not approved stays and is listed in the report as intentionally kept.

## Phase 4 — Verify and report

Confirm the end state:

- `git worktree list` — only CHECKOUT; any linked worktree is gone
- `git branch -a` — only TARGET, `origin/TARGET`, `origin/HEAD`, plus items the user chose to keep
- `git status` — clean, and not ahead of/behind origin/TARGET

Report concisely: what landed on TARGET (commit subjects), how many local/remote branches and worktrees were removed, and anything kept with its reason. If any verification line fails, say exactly which and why instead of declaring success.

If any git command fails unexpectedly along the way (rejected push, refused worktree removal, blocked checkout), read `references/troubleshooting.md` for the resolution steps before improvising.

## Operational constraints

- Push TARGET only as a fast-forward — a `--force` push can erase work already landed on the shared branch.
- Keep TARGET itself alive, locally and on origin — it is never a cleanup candidate.
- Get per-item user approval (Phase 3d) before any forcing form: `git branch -D`, `git worktree remove --force`, or deleting an unmerged/foreign remote branch.
- Commit exclusively through `commit-changes` (Phase 1) — raw `git add`/`git commit` bypasses its safe-staging rules.
- Surface changes found in the main checkout or a dirty worktree instead of stashing, resetting, or discarding them — they are not this session's to lose.
- Enter Phase 3 only after the Phase 2 ancestor check passes, because cleanup deletes the branches holding any unlanded work.
