---
name: write-readme
description: Creates, improves, or reviews README files, inspecting the repo first. Use for write/update/review a README. NOT for CLAUDE.md (edit-claude-md) or docs sites.
argument-hint: "[repo or README path, plus optional focus]"
allowed-tools: Read, Write, Edit, Grep, Glob, AskUserQuestion, Bash(curl *), Bash(ls *), Bash(git *)
---

Create a README from scratch, improve an existing one, or review one against a graded checklist — grounded in a synthesis of 30+ authoritative sources (standard-readme, Art of README, the ddbeck checklist, Google/Microsoft/18F style guides, Diátaxis, Cornell/Tilburg research-data guidance).

## When NOT to use this skill

- CLAUDE.md or agent instructions — use `edit-claude-md`.
- A docs site, wiki, or multi-page documentation — the README links to those; it doesn't replace them.

## Two rules that decide everything

Before anything else, hold these two rules. Every step below serves them.

1. **A README is an orientation artifact, not the manual.** Its job is to let a stranger decide in seconds whether the project fits their need, then hand off. Order content as a cognitive funnel — name, what/why, then progressively narrower detail — so the reader can bail out at every step with a valid answer. The README is the lobby, not the library: link out for depth.
2. **Every fact comes from the repository or the user — never from imagination.** Inspect the repo before writing a word. IF a claim (install command, flag, version, badge, benchmark) cannot be traced to a file you read or an answer the user gave, THEN it must not appear — ask, or leave a `<needs input: …>` placeholder.

## Decide the mode

The input is `$ARGUMENTS` when invoked as a command, otherwise the current request and conversation.

- **Create** — no README exists, or the user asks for one from scratch.
- **Edit** — a README exists and the user wants it changed or improved.
- **Review** — the user wants an assessment only ("review/audit/grade this README"). Review never modifies the file.

IF the request leaves the mode ambiguous (e.g. "look at my README"), THEN confirm it with `AskUserQuestion` before doing anything heavier than reading — guessing Edit when the user wanted Review rewrites a file nobody asked you to touch.

## Create workflow

1. **Inspect the repository first** — it yields most of the factual content:
   - Manifest (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, …): name, description, version, license, entry points, scripts.
   - `LICENSE`, `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`, `docs/`.
   - CLI entry points (`bin`, `[project.scripts]`, argparse/click/clap/cobra usage).
   - CI config (which badges would be honest), install scripts, Makefile, Dockerfile.
   - Tests — usually the clearest usage examples.
2. **Detect the artifact type** (library, CLI tool, application/service, internal repo, data/research) and pick sections from `{baseDir}/references/section-menu.md`. It is a menu, not a fill-in-the-blank template — omit sections the project doesn't need.
3. **Ask only what the code can't answer**, at most these five: problem + audience, project status, support channel, contribution policy, anything to exclude. When the user isn't available, leave `<needs input: …>` markers.
4. **Draft** in the menu's default order, following the writing rules in `{baseDir}/references/style-and-antipatterns.md`. Write the one-line description last — it's the hardest part (scaffold: "With PROJECT you can VERB NOUNS").
5. **Run the verification gate** below before presenting.

## Edit workflow

1. **Read the whole README**, then audit it against `{baseDir}/references/review-checklist.md`.
2. **Inspect the repo for drift**: install commands vs manifest, example imports vs source, badge URLs, links, stated license vs LICENSE file, hardcoded versions, screenshot age.
3. **Classify the scope**: **patch** (structure sound, facts stale or gaps), **restructure** (what/why buried under detail — funnel violated), or **rewrite** (stub or fundamentally wrong — switch to the Create workflow, salvaging good content).
4. **Preserve the author's voice**: keep tone, formatting idioms, and section names that work; don't add sections the author deliberately omitted unless asked.
5. Apply blocking fixes first, run the verification gate, then present a short summary of what changed and why.

## Review workflow

1. Read the README completely and inspect the repo (same drift checks as Edit) — ground every finding in the actual text and files *before* loading the checklist.
2. Run the full checklist in `{baseDir}/references/review-checklist.md` plus the verification gate.
3. Output findings ranked **Blocking / Important / Advisory**, plus a **Verified OK** list — each finding names the problem, where it is, and the concrete fix. Do not touch the file.

## Verification gate (all modes)

Mechanical checks — verify with tool output, never judgment:

| Check | How |
|---|---|
| Relative links and anchors | Linked file exists (Glob); anchor matches a real heading |
| External links | `curl -sIL -o /dev/null -w "%{http_code}" <url>` returns 2xx/3xx |
| Install command | Package name matches the manifest |
| Title | First H1 matches repo/manifest name |
| Short description | Matches the manifest description field |
| Usage example | Imported symbols exist in source (Grep) |
| Length | Over ~100 lines → ToC present and its links resolve |

IF a check fails in Create/Edit, THEN fix it before presenting. IF it fails in Review, THEN report it as Blocking. IF external links can't be checked (offline), THEN say so — never silently skip.

## Edge cases

- **Monorepo** — the root README orients across packages and links to per-package READMEs; don't duplicate their content.
- **Profile or org README** — a different genre (branding, links), not project documentation; confirm intent before applying this structure.
- **No manifest** (scripts, configs, notes) — derive what/why from the files themselves and lean harder on the five questions.
- **README in another language** — keep the original language unless asked.
- **Review finds a good README** — say so plainly and suggest only the highest-value tweaks; don't manufacture findings.

## References

Load only what the current step needs — these stay out of context until then.

- `{baseDir}/references/section-menu.md` — the three-tier section menu, per-artifact-type deltas, default ordering, and where sources disagree.
- `{baseDir}/references/style-and-antipatterns.md` — the writing rules, the anti-pattern catalog with detector signals, and rot signals for edits and reviews.
- `{baseDir}/references/review-checklist.md` — the graded MUST/SHOULD/MAY checklist, the review output format, and the mechanical checks in detail.

## Hard prohibitions

- Never invent a fact — every install command, flag, version, badge, or claim traces to a file read or a user answer, because a wrong command costs the reader more than a missing one.
- Never modify the file in Review mode — the deliverable is findings; unrequested edits destroy trust in the review.
- Never inline content that has a dedicated home (full changelog, complete API reference, contributing guide) — link instead, because duplicated content rots in two places.
- Never flatten the author's voice in Edit mode — wholesale rewrites need an explicit ask, because the README is the author's front door, not yours.
- Never use marketing superlatives ("blazingly fast", "seamless") — state facts or show benchmarks, because untestable claims erode trust in the testable ones.
