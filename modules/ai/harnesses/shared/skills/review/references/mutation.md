# Mutation testing in a throwaway clone

Loaded at Step 3b. Mutation testing changes the changed lines and checks that a test fails. A
mutant that survives is a test gap. It runs the project's code, so it runs only on the user's own
code and only in a clone made for the purpose.

Contents: own code only; the clone; the tool; the box; integrity; lifetime; output; caveat.

## Own code only

Run for `working` and `staged`. For every other target, run only when every commit has the author
email of `git config user.email`:

| Target | Check |
|---|---|
| `since REV` | `git log --format=%ae REV..HEAD` |
| `branch` | `git log --format=%ae "$(git merge-base "$default" HEAD)"..HEAD` |
| `A..B` | `git log --format=%ae A..B` |
| single ref | `git log -1 --format=%ae REF` (without `-1`, `git log REF` walks the whole history) |

Skip `pr`, `D123` and anything else, and report `mutation: skipped (not the user's own code)`.
`gh pr checkout` makes a PR look local, which is why locality is not the test.

## The clone

`C` is `<scratchpad>/review/mutation/repo`.

1. `git clone --local --no-hardlinks --no-checkout "$(git rev-parse --path-format=absolute --git-common-dir)" C`.
   `--no-hardlinks` keeps the clone's object files off the source's inodes, so a tool that rewrites
   them cannot reach the real repository. Check once: `find C/.git/objects -type f -links +1` prints nothing.
   Never `cp -R` the tree (a linked worktree's `.git` file points back at the source repository) and
   never `git worktree add` (it registers in the source `.git`). Then `git -C C remote remove origin`,
   because the clone's config would otherwise name the real repository's path to anything that
   reads the clone. Then delete `C/.git/logs`: the clone's reflog records `clone: from <real path>`,
   and auditors read the clone.
2. When the source has `core.sparseCheckout` true, mirror it before the checkout:
   `git -C C sparse-checkout init --cone` (or `--no-cone` when `core.sparseCheckoutCone` is false),
   then `git sparse-checkout list | git -C C sparse-checkout set --stdin`.
3. `git -C C checkout --detach <head commit>`: HEAD for `working`, `staged` and `since`, the head
   commit for the others.
4. For `working`, `since` and `staged`, materialize the uncommitted part with one exact patch, so
   renames, deletions, modes, symlinks and binary files all come across:
   `diff-metrics diff --repo <src> --base HEAD (--worktree | --index) --binary > <scratchpad>/review/mutation/target.patch`,
   then `git -C C apply --binary <that patch>` (add `--index` for `staged`). A failed apply, or a patch that changes a submodule
   (`Subproject commit`), makes mutation `unmeasured (<reason>)`.
5. Check the clone against the target, read-only:
   - `branch`, ranges and single refs: `git -C C rev-parse HEAD` equals the head commit and
     `git -C C status --porcelain=v1 -z --untracked-files=all` is empty.
   - `staged`: `git -C C diff --cached --name-only -z --no-renames HEAD` lists the same paths as the
     source's (`GIT_OPTIONAL_LOCKS=0`, same command).
   - `working` and `since`: split `diff-metrics diff --repo <dir> --base HEAD --worktree --binary` at each
     `diff --git` line, sort the chunks and hash them, for the source and for C; the digests must match.
     Sorting matters: a staged new file sits among the tracked files in the source and among the
     untracked ones in C. (`snapshot` would write objects into the source.)

   A mismatch is `unmeasured (clone does not match the target)`. Record `diff-metrics fingerprint --repo C`
   and the sha256 of `C/.git/config` and of the files under `C/.git/hooks` as the clone's baseline.

## The tool

Use the project's own first: a Stryker config, `[tool.mutmut]`, `.cargo/mutants.toml` or
cargo-mutants in CI, the pitest plugin in `pom.xml` or Gradle, `.gremlins.yaml`. Otherwise take one
from nixpkgs through `nix shell nixpkgs#<attr>` after confirming the attribute exists
(`nix eval --raw nixpkgs#<attr>.version`).

Mutate changed lines only, with the tool's own diff or line filter as its `--help` shows it, for
example `cargo mutants --in-diff <file>`. A tool with no such filter is
`unmeasured (<tool> has no changed-line filter)`. Never mutate whole files and filter afterwards:
the run would cost many times more and its survivors would describe code this change did not touch.

## The box

```bash
diff-metrics timebox --seconds 600 --cwd <C or the subdirectory the tool needs> \
  --stdout <scratchpad>/review/mutation/run.out --stderr <scratchpad>/review/mutation/run.err -- <tool command>
```

The tool runs as the leader of a new session. At its end `timebox` kills the whole group and then
every process still carrying its environment token, so a daemon that left the group (a Gradle or
Jest worker started with `setsid`) dies too. Ten minutes keeps a review usable on every run; exit 124
means the box fired: report what the tool wrote as `partial`, never as clean. `timebox` owns the
process group, so no `pkill -f` is needed (a pattern match would also kill the shell that runs it).
Run it in the background and wait (SKILL.md Step 3b).

Residual risk: a process that both leaves the session and clears its environment survives.

## Integrity after the run

Mutation tools leave caches in the clone (`__pycache__`, `mutants.out/`, `.stryker-tmp/`). Restore it
first. Compare `C/.git/config` and `C/.git/hooks` with the baseline before running any git command in
C (a changed `core.fsmonitor` would run code); a difference deletes the clone. Then `git -C C reset --hard`,
`git -C C clean -fdx`, and for `working`, `since` and `staged` apply the target patch again with step 4's
flags (`--index` for `staged`). Recompute `diff-metrics fingerprint --repo C`: a difference from the
baseline means the clone is deleted now, and the refuter and the auditors get no clone. Do this after
the tool, after the refuter (Step 7) and before the audit takes its own baseline (Step 7b).

## Lifetime

The clone stays until Step 7b ends, so the refuter can run a disproving check inside it and the
auditors can read it (each auditor gets its own copy, one auditor included). Before the Step 7b refuter pass, check the clone against its baseline again. When Step 7b is skipped, it ends with
Step 7. Teardown is `rm -rf "<abs C>"`; no process of the run is left, because `timebox` ended them.

## Output

`<scratchpad>/review/mutants.txt` holds one `## <file> <function> (<k> survived)` header per
function, then `metric: mutant <file>:<line> survived (<mutation>)` lines. One status line goes in
the report header:

- `mutation: measured (<tool>, <n> mutants, <k> survived)`
- `mutation: partial (cut at 10 min, ...)`
- `mutation: unmeasured (no tool for <languages>)`
- `mutation: unmeasured (<reason>)`
- `mutation: skipped (not the user's own code)`

## Caveat

Tests in the clone can still write `$HOME` caches and reach the network. The clone limits what a
test can do to the repository, not to the machine.
