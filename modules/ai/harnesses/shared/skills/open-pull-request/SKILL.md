---
name: open-pull-request
description: Creates or updates a GitHub pull request with a human-sounding title and body, no AI attribution. Use for open a PR. NOT for landing on main (merge-and-cleanup).
argument-hint: "[optional title]"
allowed-tools: Bash(git *), Bash(gh *), Bash(cat *), Bash(ls *), Bash(command *), Bash(wc *), Read, Grep, Glob, Skill, Write
---

# PR (write and open pull requests)

## When NOT to use this skill

- **Landing work directly on main** (rebase, fast-forward, branch/worktree cleanup) instead of opening a review — use `merge-and-cleanup` instead.
- **Phabricator diffs** — use the repo's diff tooling instead; this skill is GitHub-specific (`gh pr create`).

## Goal

1. Open or update a GitHub pull request for the current branch.
2. Write a title and body that read like a terse, competent human engineer wrote them. No AI tells, no marketing tone, no padding.
3. Never include any AI attribution, trailer, or metadata.
4. Respect existing repo conventions (PR templates, base branch, label style).

## Pre-flight

Run these in parallel:

- `git status --porcelain=v1`
- `git branch --show-current`
- `gh repo view --json defaultBranchRef -q .defaultBranchRef.name` (base branch; fall back to `main` if this fails)
- `git log --oneline <base>..HEAD` (commits on this branch)
- `git diff <base>...HEAD --stat` (diff shape)
- `git diff <base>...HEAD` (actual changes, for drafting the body)
- `gh pr view --json number,title,body,state,url 2>/dev/null` (does a PR already exist?)
- `ls .github/pull_request_template.md .github/PULL_REQUEST_TEMPLATE.md .github/PULL_REQUEST_TEMPLATE/ 2>/dev/null`
- `command -v gh >/dev/null 2>&1` (is gh installed)

Stop and ask if any of these are true:

- Current branch equals the base branch. A PR from `main` into `main` is nonsense.
- Zero commits ahead of the base. Nothing to PR.
- `gh` is not installed or not authenticated. Tell the user to run `gh auth login`.

## 1. Handle uncommitted changes

If `git status --porcelain=v1` has output:

1. Show the user what is uncommitted.
2. Ask: "There are uncommitted changes. Commit them first (via the commit-changes skill) and include in the PR, or leave them out?"
3. If the user says include, invoke the `commit-changes` skill, then continue.
4. If the user says leave out, continue with only what is already committed.

Never stash. Never `git add -A` without explicit approval from the user.

## 2. Push the branch

If the current branch has no upstream, or is ahead of its upstream:

```bash
git push -u origin HEAD
```

If push fails, stop and report the error. Do not retry with force.

## 3. Existing PR?

If `gh pr view` returned a PR for this branch:

1. Report the existing PR number, title, and URL.
2. Ask: "PR already exists. Update the title and body to match the current state, just re-sync by pushing new commits, or leave it alone?"
3. If the user wants to update body or title, draft new content per section 5, then run one or both of:
   ```bash
   gh pr edit <N> --title "<new title>"
   gh pr edit <N> --body-file /tmp/pr-body.md
   ```
4. If the user only wants to push new commits, you already did that in step 2. Stop.

Otherwise proceed to section 4.

## 4. Size check

Count added plus deleted lines from `git diff <base>...HEAD --stat` (the last line includes a total).

- Under ~400 lines: proceed.
- 400 to 1000 lines: warn the user. "This PR is about N lines. Large PRs get sloppier reviews. Proceed, or split it first?"
- Over 1000 lines: stop and ask. "This PR is about N lines. That is too large for a careful review. Split into smaller PRs, or proceed anyway?"

Soft warning, not a block. The user may have a reason.

## 5. Write the title and body

### Title rules

1. Imperative mood. "Add OAuth flow", not "Added OAuth flow" or "Adds OAuth flow".
2. Aim for 50 characters, hard cap 72. PR titles often become squash-merge commit subjects.
3. No trailing period.
4. No emoji. No decorative prefix.
5. If the repo uses Conventional Commits (check recent `git log --oneline`), match that format: `type(scope): description`.
6. If `$ARGUMENTS` was provided, use it verbatim as the title.
7. Otherwise derive the title from the commits and diff. Prefer intent over file names.

### Body structure

**If the repo has a PR template** (`.github/pull_request_template.md` or similar), use it as the skeleton. Fill in every section. If a section does not apply, write `n/a` or a one-line note. Do not delete sections. Do not add unrequested sections.

**Otherwise**, use this minimal template:

```markdown
## Why

<One or two sentences. The problem or motivation. What forced this change.>

## What changed

- <specific bullet, file-level or behavior-level>
- <another bullet>

## How to test

1. <concrete step>
2. <expected result>

## Notes

<Only if there is something non-obvious: a tradeoff, a limitation, a rollback
concern, a follow-up. Delete the section entirely if there is nothing to say.>
```

**Issue linking:** if the user provided an issue number, or one is obvious from the branch name (`fix/issue-123-...`), add `Closes #N` on its own line at the very bottom of the body. Nothing more.

### Writing style (MANDATORY)

The body and title must read like a tired human engineer wrote them at 4pm on a Thursday. Not like an AI told to "write a comprehensive PR description".

**Banned phrases and openings:**

- No "This PR ..." openings. Open with the problem or the change itself.
- No "comprehensive", "robust", "seamless", "leverage", "utilize", "ensure that", "in order to", "a wide range of", "cutting-edge", "state-of-the-art".
- No "It is worth noting", "Notably", "Importantly", "Firstly", "Overall", "In conclusion", "To summarize".
- No "Let me know if you have any questions", "Happy to discuss", "Feel free to reach out".
- No "I've also", "I've made sure to", "I took the liberty of", "As requested".
- No rule-of-three marketing phrasing like "fast, simple, and reliable" or "clean, modern, and efficient".
- No motivational adjectives: "powerful", "elegant", "clean", "modern", "intuitive", "delightful".
- No restating the same point twice with different words.
- No summary paragraph at the end that repeats what the body already said.

**Banned characters. Plain ASCII only:**

- No em dash (the long one).
- No double-hyphen `--` used as a sentence dash. Use a period, parentheses, or a colon instead.
- No en dash.
- No curly or smart quotes. Use straight `"` and `'`.
- No unicode ellipsis. Use three periods if truly needed.
- No unicode bullets, arrows, checkmarks, or decorative symbols. Markdown `-` bullets only.
- No emoji anywhere in the title or body.

**Positive style rules:**

- Short sentences. Fragments are fine. Mix sentence lengths.
- Concrete over abstract. "Redis times out after 5s" beats "improved Redis reliability".
- Active voice. "Drops the old cache key on write" beats "The old cache key is dropped on write".
- Specific file names, function names, numbers. Not "several files", not "various improvements", not "a few tweaks".
- One-liners are allowed. If the PR is a one-line fix, the body can be one sentence. Do not pad.
- Leave out what is obvious from the diff. Reviewers can read code.
- Do not explain the `what` when the diff already shows it. Explain the `why`.

### Good vs bad examples

**Bad (AI style):**

> This PR introduces a comprehensive refactoring of the authentication module to enhance security, improve maintainability, and ensure seamless integration with the existing session handling logic. The changes leverage modern patterns to provide a robust foundation for future development.

**Good (human):**

> Login was writing the user ID to the JWT and to Redis in two separate steps, and they drifted on retry. Moved the Redis write into the login transaction. Also deleted `legacySessionShim`, nothing has called it since the v2 cutover.

**Bad:**

```
## What changed
- Made various improvements to error handling
- Enhanced logging throughout the service
- Refactored several files for better maintainability
```

**Good:**

```
## What changed
- `auth/session.go`: wrap the Redis write in the login tx
- Delete `auth/legacy_shim.go`, unused since v2
- One regression test in `session_test.go` covering the retry path
```

**Bad:**

> ## How to test
> Run the test suite and verify that all tests pass. Ensure the application behaves as expected under normal conditions.

**Good:**

```
## How to test
1. `go test ./auth/...`
2. Log in, kill Redis mid-request, log in again. The second login should succeed with no stale session.
```

## 6. Create the PR

Write the body to a tempfile using a quoted heredoc so nothing expands:

```bash
cat > /tmp/pr-body.md <<'PR_BODY_EOF'
<body text here, already passed through the style rules>
PR_BODY_EOF
```

Then create the PR:

```bash
gh pr create --title "<title>" --body-file /tmp/pr-body.md --base <base>
```

Add `--draft` only if the user explicitly asked for a draft.

After creation, report the PR URL from `gh pr create` output. Nothing else. No congratulations, no next-steps list.

## AI attribution: BANNED

Under no circumstance include any of these in the title, body, commits, or anywhere else touched by this skill:

- `Co-Authored-By:` for any AI, model, tool, or assistant.
- `Assisted-By:`, `AI-Assistant:`, `Generated-By:`, or any custom AI trailer.
- Phrases like "Generated with", "Written with help from", "Powered by", "With assistance from", or any other reference to an AI having been involved.
- Any tool name, model name, or assistant name as author, co-author, or contributor.

The human who opens the PR is the sole author. No exceptions.

## Hard prohibitions

Never, as part of this skill:

- `git push --force`, `git push -f`, `git push --force-with-lease` unless the user explicitly asks.
- `git rebase`, `git reset --hard`, `git commit --amend` (not part of opening a PR).
- `git stash` (touches unrelated work).
- `git restore`, `git checkout -- ...`, `git clean`.
- Invent test results, claim things were verified when they were not, or describe behavior you did not observe.
- Any AI attribution of any form (see section above).
- Unicode punctuation in any output (em dash, en dash, smart quotes, ellipsis, decorative symbols, emoji).
- `--` as a sentence dash in the PR title or body.
- AI-style prose (see banned phrases list in section 5).
- Padding the body to look thorough. Terse is correct. Blank sections get deleted, not filled with filler.
- Mixing unrelated concerns into the same PR. If the branch has two unrelated changes, warn the user and offer to split.

## Error cases

| Situation | Action |
|-----------|--------|
| On the base branch (main/master) | Stop. Ask the user to create a feature branch first. |
| Zero commits ahead of base | Stop. Report that there is nothing to PR. |
| `gh` not installed or not authenticated | Stop. Tell the user to install or run `gh auth login`. |
| `git push` fails | Stop. Report the error. Never force-push. |
| PR already exists for this branch | Report and ask whether to update or leave alone. |
| Diff over 1000 lines | Warn and ask whether to proceed or split first. |
| Repo has a PR template | Fill the template. Do not replace or delete its sections. |
| Uncommitted changes present | Ask before committing. Delegate to the `commit-changes` skill. |
