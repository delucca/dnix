# Measuring the change with diff-metrics

Loaded at Step 3. `diff-metrics` is a deterministic, read-only script. It turns the target diff into
`metrics.json`: size facts, tripwires, ranked pointers and a per-check status. It decides nothing
about the review; lenses and the refuter do.

Contents: running it; verbs; target flags; checks; tripwire severities; schema; the `metric:` label; freshness; failure modes.

## Running it

Use the `diff-metrics` binary on PATH. Without it, run the same script by the shared path contract,
which is identical under Claude Code, Codex, agy and devpods:

```bash
python3 -I ~/.config/ai/common/skills/review/scripts/diff_metrics.py <verb> ...
```

The script needs Python 3.9+. lizard and scc come from `skill.nix`, so an unswitched machine or a
devpod measures less and says so: a check whose tool is missing is `unmeasured` with the reason.

## Verbs

| Verb | Use |
|---|---|
| `diff --repo DIR --base REV (--worktree \| --index \| --head REV) [--binary]` | The canonical unified diff of a local target. It pins every git output knob (no external diff, no textconv, no color, fixed prefixes, quoted paths), so the result is a patch even under the user's difftastic config. `--worktree` appends untracked files as new-file hunks. `--binary` makes it applicable with `git apply --binary`. |
| `measure --diff FILE --out FILE [--repo DIR] [--base REV] [--worktree \| --index \| --head REV] [--coverage FILE]` | Writes `metrics.json` and prints three lines: the totals, the unmeasured checks, the path written. |
| `bundle --metrics FILE --diff FILE --dir DIR` | Writes `stat.txt`, `pointers-correctness.txt`, `pointers-tests.txt`, `pointers-simplicity.txt`, `pointers-architecture.txt`, `added.diff` and `tripwires.md` for the lenses. |
| `filter-lint --metrics FILE` | Reads lint output on stdin and keeps the lines on changed lines. The last stderr line is `filter-lint: kept=K located=M unlocated=N`. |
| `fingerprint [--repo DIR]` | One sha256 over HEAD, the index entries and the content of tracked and untracked files. It does not see ignored files or anything under `.git`. |
| `dirty [--repo DIR] --out FILE` | Writes every dirty path, NUL separated, renames as a deletion plus an addition. |
| `commit-set [--repo DIR] --from TREE --to TREE --dirty FILE --out FILE` | Writes the paths the gate verified: changed between the trees (rename detection off) plus the dirty list, minus paths in neither the worktree nor the index. |
| `timebox --seconds N [--stdout F] [--stderr F] [--cwd D] -- CMD...` | Runs CMD in a new session under a time limit and kills the whole group, then any escaped process that still carries its environment token. Exit 124 means the limit fired. |
| `snapshot --repo DIR --index-dir DIR` | Prints the tree id of the working state through a temporary index. It writes blob and tree objects, so `review` never calls it; the push gate does. |

Every verb except `snapshot` leaves the repository untouched. Exit 0 whenever the verb ran, 2 on a
usage or input error.

## Target flags for `measure`

| Review target | Flags |
|---|---|
| `working` | `--base HEAD --worktree` |
| `since REV` | `--base REV --worktree` |
| `staged` | `--base HEAD --index` |
| `branch` | `--base "$(git merge-base "$default" HEAD)" --head HEAD` |
| `A..B` | `--base A --head B` |
| `A...B` | `--base "$(git merge-base A B)" --head B` |
| single ref | `--base REF^ --head REF` |
| `pr N` | `--base <merge base of baseRefOid and headRefOid> --head <headRefOid>` when both commits are local, else no flags |
| `D123` | no flags |

With no flags and no repository, `measure` runs the diff-only checks and reports the content checks
as unmeasured ("base not in the local clone"). Pass the same `--repo` the diff came from.

## Checks

| Check | Output | Languages | Known false positives |
|---|---|---|---|
| tripwires | grouped by file and kind | all (patterns per language family) | a renamed test reads as deleted plus new; helper-based assertions read as "no assertion"; a suppression string in code that quotes it is ignored only inside a string literal |
| complexity | functions whose cyclomatic complexity rose, and new functions, with before and after | lizard's readers: py, js, ts, go, rs, java, kt, swift, c, cpp, cs, rb, php, scala, lua and more; not nix, sh | a renamed function reads as new |
| hotspots | changed files in the top decile of churn times complexity over the last 1000 commits | scc's languages | none known; unmeasured on a shallow clone or without a commit base |
| duplicates | added blocks that repeat existing code (4-line window repo-wide, lizard token duplicates among the changed files) | all text languages | boilerplate that repeats by design |
| comments | added comment lines, classified comment, code or directive; plus scc's per-file comment delta | languages with a known comment marker | commented-out code is a heuristic; trailing comments and docstrings are not detected |
| dependencies | new dependency names (bumps excluded) | package.json, requirements, go.mod, Cargo.toml, pyproject.toml, Gemfile | a dependency moved between sections is not new |
| uncovered | changed lines a handed-in coverage report marks uncovered | lcov, Go coverprofile, plain `path:line` | non-executable lines are never listed |

A generated-file marker in the first five lines excludes a file from S and F, duplicates and
complexity only when the file already carried it at base; a test file or a gate config file is never
excluded, so one comment line cannot switch off its tripwires. Extensions outside the language map
count under `other` and, when lizard has no reader for them, appear in the complexity check as
unmeasured. Coverage is judged per language: `checks.uncovered.languages` gives each changed language `measured`,
`no evidence` or `not coverable` (Nix, shell, Make, Docker, SQL and config formats unless the report
includes them). A report with no line data, or without evidence for a coverable changed language, makes
`uncovered` unmeasured with `applicable: true`; a change with no coverable language makes it unmeasured
with `applicable: false`, which the gate reads as not-applicable. A diff that names an absolute path or one with `..` is refused (exit 2).

## Tripwire severities

A tripwire group goes straight to the refuter as a candidate. The table fixes its severity, because
the refuter never adjusts one.

| Kind | Severity | Why |
|---|---|---|
| `test-deleted` | major | removing a test is the cheapest way to make a gate pass |
| `test-skipped` | major | a skipped or focused test silently stops guarding |
| `assertion-lost` | major | fewer assertions in a test file weaken what the test proves |
| `test-no-assertion` | major | a new test without an assertion passes whatever the code does |
| `gate-loosened` | major | weakening lint, coverage or CI settings is the other route around a gate |
| `suppression` | minor | `# noqa`, `@ts-ignore` and the like are often legitimate; the reviewer decides |

## Schema (version 1)

```json
{
  "schema": 1,
  "tools": {"diff_metrics": 1, "git": "2.54.0", "lizard": "1.22.1", "scc": "3.7.0"},
  "target": {"diff_sha256": "9f2c...", "repo": "/abs/repo", "base": "3a93171...", "head": "worktree", "coverage_sha256": null},
  "facts": {
    "S": 42, "F": 3, "added": 30, "deleted": 12,
    "excluded": ["Cargo.lock"], "binary": [],
    "changed_lines": {"src/a.py": [[10, 14], [30, 30]]},
    "files": {"src/a.py": {"status": "modified", "language": "python", "test": false, "added": 6, "deleted": 2, "excluded": false}},
    "languages": {"python": 2, "nix": 1},
    "tests_touched": true
  },
  "checks": {
    "tripwires": {"status": "measured"},
    "complexity": {"status": "partial", "unmeasured": {".nix": "lizard has no reader for .nix"}},
    "hotspots": {"status": "unmeasured", "reason": "shallow clone"},
    "duplicates": {"status": "measured"},
    "comments": {"status": "measured"},
    "dependencies": {"status": "measured"},
    "uncovered": {"status": "unmeasured", "reason": "no coverage handed in"}
  },
  "tripwires": [
    {"kind": "suppression", "severity": "minor", "file": "src/a.py",
     "items": [{"line": 12, "base_line": null, "detail": "# type: ignore", "text": "x = f()  # type: ignore"}]}
  ],
  "pointers": {
    "complexity": [{"file": "src/a.py", "function": "parse", "line": 10, "before": 4, "after": 9, "status": "changed"}],
    "hotspots": [{"file": "src/a.py", "rank": 3, "of": 120, "churn": 340, "complexity": 55}],
    "duplicates": [{"file": "src/b.py", "line": 20, "lines": 6, "match": {"file": "src/util.py", "line": 88, "where": "base"}, "source": "window"}],
    "comments": [{"file": "src/a.py", "line": 13, "kind": "comment", "text": "# loop over items"}],
    "comment_deltas": [{"file": "src/a.py", "delta": 2}],
    "dependencies": [{"file": "package.json", "line": 4, "name": "left-pad", "spec": "1.3.0"}],
    "uncovered": [{"file": "src/a.py", "lines": [14, 30]}]
  }
}
```

`S` and `F` exclude lockfiles, vendored trees, generated files and binaries; `facts.excluded` names
them. A check is `measured`, `partial` (some extensions or files could not be read) or
`unmeasured` (with a reason). An unmeasured check is never clean.

## The `metric:` label

A pointer or tripwire line a lens quotes is evidence labelled `metric: <check> <file>:<line> <detail>`,
quoted exactly as `diff-metrics bundle` wrote it. Two examples:

- `metric: complexity src/parse.py:10 parse 4 -> 9 (changed)`
- `metric: mutant src/parse.py:31 survived (replaced < with <=)`

A metric says what is there. It is not a target, and no lens files a finding on a number alone.

## Freshness

Use a handed-in `metrics.json` only when all of these match what this run just resolved:
`target.diff_sha256` equals the sha256 of its own `target.diff`, `target.repo` is its toplevel,
`target.base` its resolved base (or both null), `target.head` is `worktree`, `index` or the same
SHA, and `schema` is 1. Anything else is stale: run `measure` again and say "stale metrics.json
ignored". The same rule applies to `claim.txt`, which counts only when its first line is
`diff-sha256: <the same hex>`.

## Failure modes of the measurement, mutation and audit steps

| Situation | Action |
|---|---|
| `diff-metrics` not on PATH | Run the script by the path contract (`references/metrics.md`) |
| lizard or scc missing | The check is unmeasured with the reason; never clean |
| Python 3 missing | Every metric check is unmeasured and there are no tripwires; say so |
| Handed-in `metrics.json` or `claim.txt` is stale | Ignore it, re-run, say so |
| Mutation tool missing or without a changed-line filter, time box hit, clone does not match the target | `mutation: unmeasured` or `partial` with the reason |
| No `~/.config/ai/review-lenses/` folder | "extra lenses: none installed" |
| An extra lens probe fails | Do not spawn it; name its `unavailable` message in the cost line and header |
| Harness unknown | Session model; every available auditor |
| An auditor is unavailable, timed out, unreadable or discarded, or its CLI is blocked by the harness's own sandbox | Name it in the Audit line as unavailable; never clean |
