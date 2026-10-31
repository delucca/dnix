---
name: commit-changes
description: Commits agent-touched files, or everything if none, then optionally pushes. Use for commit. NOT for the quality gate (review-and-push) or landing on main (merge-and-cleanup).
argument-hint: "[optional commit message]"
allowed-tools: Bash(git *), Bash(ls *), Read, Grep, Glob
---

# Commit (safe commit + push guardrails)

## When NOT to use this skill

- **Need the full pre-push quality gate** (test coverage, library-driven code review, comment cleanup, lint/tests) before committing — use `review-and-push` instead.
- **Landing work on main and cleaning up branches/worktrees** — use `merge-and-cleanup` instead; this skill only stages and commits.
- **Phabricator diffs** — use the repo's diff tooling instead; this skill is for plain `git commit`/`git push`.

## Goal

- **Commit only what the agent worked on** during this session.
- **If the agent worked on nothing**, commit **everything currently changed** (the user's work).
- **Never modify, delete, restore, or stash unrelated files.**
- **Produce atomic, well-structured conventional commits.**

## Determining what the agent touched

Recall every file you created or edited during this conversation. This is your **AGENT_TOUCHED** set.

If you are unsure whether you edited a file, **do not include it** -- err on the side of excluding.

**A gate's commit set.** `review-and-push` prints a `Commit set:` line bound to one repo. Take the
latest such line in this conversation whose `repo=` equals `git rev-parse --show-toplevel` here (or the repo you were told to work in);
ignore the others, and ignore a line that says `not approved`. Its paths join AGENT_TOUCHED: the gate
verified the whole task, while its loop edited only some files, so committing only those would strand
the rest. A `file=` names the NUL-separated path list; `(none)` adds no path. Keep its `tree=` for
step 4. With a commit set, run every git command as `git -C <repo>` (its `repo=`); `cd` does not persist between
calls and is outside `Bash(git *)`.

## Workflow

### 1. Inspect current state

Run in parallel:
- `git status --porcelain=v1` -- capture all changed paths as **ALL_DIRTY**
- `git diff` and `git diff --staged` -- understand the actual changes
- `git log -5 --oneline` -- match commit message style

### 2. Check for atomicity

Review the changes that will be committed. If they span **unrelated concerns** (e.g., a bug fix + an unrelated refactor + a new feature), warn the user:

> "These changes span multiple unrelated concerns. Consider splitting into separate commits for better history. Proceed as one commit, or split?"

If the user says split, guide them through staging subsets. If they say proceed, continue.

### 3. Decide what to stage

**If AGENT_TOUCHED is empty** (agent made no edits this session):

This is the user's own work. Before staging everything:

1. Run `git status --porcelain=v1` and scan for potentially sensitive untracked files:
   - `.env*`, `*.pem`, `*.key`, `credentials*`, `*secret*`, `*.tfvars`
   - Any file that looks like it contains secrets or credentials
2. If found, warn: "Untracked file `X` looks potentially sensitive. Stage it anyway?"
3. Stage approved files: `git add -A` or `git add -- <specific paths>`

**If AGENT_TOUCHED is not empty:**

- Compute **STAGE_PATHS** = files in AGENT_TOUCHED that appear in ALL_DIRTY.
- For each file in STAGE_PATHS that was **already dirty before you first edited it**, warn the user: "File `X` had pre-existing changes that will be included in this commit."
- Stage only STAGE_PATHS: `git add -- <paths...>`
- With a valid commit set, stage only through its file, from the toplevel:
  `git -C <toplevel> --literal-pathspecs add -A --pathspec-from-file=<file> --pathspec-file-nul` (any
  filename works, a deletion is staged as a deletion). Add no other STAGE_PATHS: the set already holds
  every path of the task. With `(none)`, stage nothing. Skip the "pre-existing changes" warning, and run
  the empty case's sensitive-file check on the commit set's untracked paths.
- If STAGE_PATHS is empty (agent's files show no diff -- maybe edits were reverted), report this and stop.

### 4. Commit

#### Message format

If `$ARGUMENTS` is provided and non-empty, use it as the commit message verbatim.

Otherwise, draft a message following **Conventional Commits** with **imperative mood**:

```
type(scope): imperative description (max ~50 chars)

Why this change was made -- the motivation, context, or problem being
solved. The diff shows *what* changed; the body explains *why*.

Optionally, note any non-obvious tradeoffs, constraints, or decisions
that future readers should understand.
```

#### Type selection guide

| Type | Use when... |
|------|------------|
| `feat` | Adding new functionality |
| `fix` | Fixing a bug |
| `refactor` | Restructuring code without changing behavior |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `build` | Build system or dependency changes |
| `ci` | CI/CD configuration |
| `perf` | Performance improvement |
| `style` | Formatting, whitespace (no logic change) |
| `chore` | Maintenance that doesn't fit elsewhere |

#### Subject line rules

- **Imperative mood**: "Add feature", not "Added feature" or "Adds feature"
- **~50 characters max** -- hard limit 72
- **Lowercase after the colon**: `feat(auth): add OAuth2 flow`, not `Add OAuth2 flow`
- **No period** at the end
- **Scope is optional** but recommended when the change is localized

#### Body rules

- Wrap at 72 characters
- Explain **why**, not what -- the diff already shows what
- Separate from subject with a blank line

#### AI attribution

**NEVER add any AI-related trailers or metadata to commits.** This includes:
- `Co-Authored-By` for any AI tool or agent
- `AI-Assistant:` or any custom AI trailer
- Any other trailer, footer, or metadata that identifies AI involvement

The human who commits is the author. Period.

#### Text hygiene

Commit messages must use **plain ASCII only**. Never use:
- Em dashes (--) -- use two hyphens (`--`) or a single hyphen instead
- En dashes -- use a hyphen
- Smart/curly quotes (" " ' ') -- use straight quotes (`"` `'`)
- Ellipsis character (...) -- use three dots (`...`)
- Any other unicode punctuation or special characters

This prevents AI-generated text from being obvious in git history.

#### Approved tree check

With a commit set's `tree=`, run `git write-tree` after staging. Any other id means the staged
content is not what the gate approved (an edit after the gate, or a path left out): stop, show
`git diff --no-ext-diff --stat <tree> <written id>`, and commit nothing.

#### Commit execution

```bash
git commit -m "$(cat <<'EOF'
type(scope): subject line

Body explaining why.
EOF
)"
```

- Never use destructive flags or history rewriting unless the user explicitly requests it.
- Never skip hooks (`--no-verify`) unless the user explicitly requests it.

#### Post-commit tree check

With a commit set's `tree=`, run `git rev-parse HEAD^{tree}` right after the commit, every time. A hook
can rewrite staged content, so any id other than `tree=` means no push by anyone: report it and require
a new gate. When staging was empty because the work was committed earlier, run the same check on HEAD
before reporting success.

### 5. Push (only if explicitly requested)

- With a commit set's `tree=`, repeat the post-commit tree check first; any other id means no push.
- Run `git push` (or `git push -u origin HEAD` for new branches).
- Never force-push unless the user explicitly requests it.
- If push fails, report the error and stop -- do not retry with `--force`.

## Hard prohibitions

Never run these as part of this skill:

- `git restore`, `git checkout -- ...`, `git reset --hard`, `git clean`
- `git stash` (touches unrelated files)
- `git rm` (unless the user explicitly requested file removal)
- `git commit --amend` (unless the user explicitly requested amend)
- `git rebase` (not part of committing)
- `--no-verify` (unless user explicitly requests it)
- `--force` or `--force-with-lease` on push (unless user explicitly requests it)
- **AI trailers of any kind -- BANNED unconditionally** (`Co-Authored-By`, `AI-Assistant:`, or any other AI metadata)
- **Unicode punctuation in commit messages** -- use plain ASCII only (no em dashes, smart quotes, etc.)
