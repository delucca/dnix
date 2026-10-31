# Troubleshooting merge-and-cleanup

Resolution steps for the failure modes this skill hits in practice. Consult the matching entry before improvising; the Operational constraints in SKILL.md still apply here.

## `git worktree remove` refuses on a clean worktree

Usually a stale lock or an initialized submodule inside the worktree.

1. Check for a lock: `git worktree list --porcelain` shows `locked` — if the reason is stale, `git worktree unlock <path>` and retry.
2. If a submodule is the blocker, report it and ask the user — do not jump to `--force`.

## `git worktree remove` ran from inside the tree

The shell reports "no such file or directory" for every command afterwards. `cd ~/Developer`; the removal itself succeeded.

## Push rejected as non-fast-forward in Phase 2

Someone (or another session) landed on TARGET between the fetch and the push.

1. `git fetch origin` and rebase onto the new `origin/TARGET` again.
2. Retry the push once. A second consecutive rejection means the branch is actively contended — stop and report rather than looping.

## `git checkout TARGET` blocked in the main checkout

Git refuses because TARGET is already checked out in another worktree. That worktree is the real main checkout for this purpose — run the ff-merge there (`git -C <that-path> merge --ff-only origin/TARGET`) and treat the remaining checkouts as cleanup candidates as usual.

## Rebase stops on conflicts repeatedly

If a second rebase attempt hits the same conflicts, the branches have genuinely diverged. Leave the rebase aborted (`git rebase --abort`), keep the work branch intact, and hand the conflict list to the user — never resolve with `-X ours`/`-X theirs`.

## `git branch -d` refuses a branch that looks merged

The branch tip is probably not reachable from TARGET (e.g. it was squash-merged elsewhere). Treat it as unmerged: put it on the ASK list with its `git log --oneline TARGET..<branch>` sample instead of escalating to `-D` on your own.
