# Resolving a review target

Loaded at Step 2 for anything other than a plain local diff.

Contents: git semantics; local targets; GitHub pull requests; Phabricator revisions.

## Git semantics

**Find the default branch — never hardcode `main`.** Try in order, first success wins:

```bash
git symbolic-ref --short refs/remotes/origin/HEAD          # local, instant, needs the ref set
git remote show origin | sed -n '/HEAD branch/s/.*: //p'   # authoritative, one network round trip
git ls-remote --symref origin HEAD                         # last resort, also networked
```

If none of them resolves, stop and ask for the target branch: this skill never changes the repository's refs.

**What a branch introduces is three-dot, not two-dot.** The merge base against HEAD is the
committed branch work, and what GitHub shows in a PR:

```bash
git diff --no-ext-diff --no-textconv "$default...HEAD"
```

A plain two-dot diff against `"$default"` also reports everything that landed on the default branch since the
fork point, attributing other people's work to this branch.

The `--merge-base "$default"` option of the diff command is **not** an equivalent spelling. It diffs the merge base
against the **working tree**, so on a dirty tree it folds uncommitted WIP into the result. The
failure is silent and it inflates the sizing too. That is why `branch` below passes
`--head HEAD` to `diff-metrics diff`: it diffs against HEAD, never the working tree.

Two-dot `A..B` is correct for two **fixed** commits, and only there.

**Shape before content.** `diff-metrics measure` reports S, F and the per-file counts; `stat.txt`
comes from `diff-metrics bundle`. Do not parse `--numstat` output by hand: it prints `-` for both
counts on binary files, which `diff-metrics` already excludes from S.

The user's git renders diffs through an external tool, and a rendering is not a patch. Every git
command here that reads a diff, a log patch or a commit patch carries `--no-ext-diff --no-textconv`;
`diff-metrics diff` sets those and every other output knob for you.

## Local targets

Every local target is produced by `diff-metrics diff --repo <toplevel>`, which pins the git output
knobs and writes the same canonical diff the metrics read.

| Target | Flags | Claim source |
|---|---|---|
| `working` (`since HEAD`) | `--base HEAD --worktree` | none |
| `since REV` | `--base REV --worktree` | `git log --oneline REV..HEAD` |
| `staged` | `--base HEAD --index` | none |
| `branch` | `--base "$(git merge-base "$default" HEAD)" --head HEAD` | `git log --oneline "$default"..HEAD` |
| `A..B` | `--base A --head B` | `git log --oneline A..B` |
| `A...B` | `--base "$(git merge-base A B)" --head B` | `git log --oneline A..B` |
| single ref | `--base REF^ --head REF` | `git log -1 --format=%B REF` |

`--worktree` appends untracked files as new-file hunks, so a brand-new file is reviewed: a review
that misses a new file misses the whole feature. A root commit has no `REF^`; use
`--base 4b825dc642cb6eb9a060e54bf8d69288fbee4904` (the empty tree) for it.

## GitHub pull requests

```bash
gh pr view <n> --json title,body,commits,files,additions,deletions,baseRefName,baseRefOid,headRefOid,closingIssuesReferences
gh pr diff <n> > "$scratchpad/review/target.diff"
```

For the metrics, pass `--base "$(git merge-base <baseRefOid> <headRefOid>)" --head <headRefOid>` to
`diff-metrics measure`, and only when both OIDs exist locally (`git cat-file -e <oid>^{commit}`).
Never fetch to make them exist. Otherwise `measure` gets neither flag and runs the diff-only checks.
The merge base, not `baseRefOid`, because `gh pr diff` is a merge-base diff.

- `title`, `body`, and `closingIssuesReferences` are the claimed behavior the tests lens checks
  against. `additions`/`deletions` give S without parsing the diff.
- Use `baseRefOid` and `headRefOid` for any local comparison. `baseRefName` names a branch that
  moves; the OIDs are what the PR was actually opened against.
- `gh pr view --json files,commits` goes through GraphQL, which truncates large lists without
  paginating and without erroring. Do not assume it returned everything: check the returned
  counts against `additions`/`deletions`, and if they disagree, say so in the report rather than
  reviewing a silent subset. (The documented 30-per-page / 3000-file and 250-commit caps belong
  to the REST endpoints — `gh api repos/{owner}/{repo}/pulls/{n}/files` and `.../commits` — which
  is where to go when a big PR needs a complete, paginated list.)
- `gh pr diff` ignores the pager; redirect or pipe it, never leave it to a terminal.

Failure of `gh` — missing binary, `gh auth status` unauthenticated, or a 404 — stops the run.
Report the exact failure. A local diff is not a substitute for a PR.

## Phabricator revisions

Conduit has no get-by-ID endpoint: every read is a `*.search` call with an `ids` or `PHIDs`
constraint. Inside a configured working copy, `arc call-conduit` reads `.arcrc` itself, so no
token handling is needed. The chain, three calls:

```bash
echo '{"constraints":{"ids":[<n>]}}' | arc call-conduit differential.revision.search
# -> fields.title, fields.summary (the claimed behavior), and the revision's diffPHID

echo '{"constraints":{"revisionPHIDs":["<PHID>"]}}' | arc call-conduit differential.diff.search
# -> the diff's numeric id

echo '{"diffID": <id>}' | arc call-conduit differential.getrawdiff
# -> the raw unified diff
```

Each call reads JSON on stdin and writes a JSON envelope on stdout; check `error_code` in the
envelope, since a Conduit error still exits 0.

A site's `arc` wrapper may differ from upstream. Fail loudly on any `arc` error and report what the
command printed — do not improvise an alternative route to the diff.
