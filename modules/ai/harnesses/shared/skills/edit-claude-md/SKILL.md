---
name: edit-claude-md
description: Creates, updates, or audits CLAUDE.md load hierarchy and instruction budget. Use for create/update/audit CLAUDE.md. NOT for prompt wording (prompt-engineer).
argument-hint: "[path | user | project | local | audit]"
allowed-tools: Bash(ls *), Bash(wc *), Bash(cat *), Bash(test *), Bash(pwd), Bash(stat *), Bash(mkdir *), Bash(find *), Bash(rg *), Bash(grep *), Read, Grep, Glob, Write, Edit, AskUserQuestion
---

# Edit CLAUDE.md

Create, update, or audit a CLAUDE.md file so it follows 2026 best practices: every line earns its place, nothing is duplicated from code, and conditional or scoped guidance lives in `.claude/rules/` (not in CLAUDE.md).

## When NOT to use this skill

- **Reviewing or drafting the wording/quality of prompt content in general** (system prompts, tool descriptions, or the instruction text going into a SKILL.md/AGENT.md/CLAUDE.md) — use `prompt-engineer` instead. This skill owns CLAUDE.md's structure and load hierarchy, not prompt-craft quality.
- **Creating a new skill or agent from scratch** — use `create-skill` or `create-agent` instead.

## The instruction budget — why every line matters

CLAUDE.md is loaded into the context window on **every turn**, as a user message after the system prompt. Two facts drive every decision this skill makes:

1. **Frontier LLMs reliably follow ~150-200 instructions** before compliance degrades uniformly (ETH Zurich, Feb 2026). Claude Code's system prompt already consumes ~50 of those slots, leaving **~100-150 for your instructions**.
2. **Degradation is uniform** — every low-value rule dilutes every high-value rule equally. Adding "prefer camelCase" weakens "NEVER delete production data" by the same amount.

CLAUDE.md is **advisory, not enforced**. For deterministic enforcement use hooks; for org-wide blocks use managed settings; for path-scoped rules use `.claude/rules/`.

## Core principles

- **Truthfulness**: Read the actual file(s) before editing. Never invent existing content.
- **Pruning > adding**: Default to removing lines. For every line, ask: *"Would removing this cause Claude to make mistakes?"* If no, delete.
- **Specific > vague**: "Use 2-space indentation" beats "format code properly". "Run `npm test` before committing" beats "test your changes".
- **Positive > negative**: "Use named exports exclusively" outperforms "Do NOT use default exports" (~50% fewer violations in testing). Reserve negation-only for true prohibitions.
- **Rationale earns weight**: "Never force push — rewrites shared history, unrecoverable for collaborators" is weighted more heavily than bare "Never force push."
- **No code style guidelines**: Linters do this faster, deterministically, and for free. Delete every formatting rule.
- **No duplication of code-derivable info**: If Claude can grep for it, don't write it.
- **One trigger to add a line**: Claude got the same thing wrong twice — or you typed the same correction across sessions. Otherwise don't add.

## Step 0 — Determine target

Resolve `$ARGUMENTS` to a target file:

| Argument | Target |
|---|---|
| Absolute path or relative path ending in `.md` | That file |
| `user` | `~/.claude/CLAUDE.md` |
| `project` | `./CLAUDE.md` (or `./.claude/CLAUDE.md` if it exists) |
| `local` | `./CLAUDE.local.md` |
| `audit` | All CLAUDE.md files reachable from CWD upward — read-only mode |
| (none) | Use `AskUserQuestion` to choose between user / project / local / audit |

If the project root is ambiguous (no `.git` in CWD or its ancestors), ask before assuming.

## Step 1 — Inventory what's actually loaded

Before any edit, list every CLAUDE.md the harness will load. Edits must be coherent across the whole hierarchy, not just the target file.

```bash
# Walk up from CWD looking for CLAUDE.md and CLAUDE.local.md
dir=$(pwd)
while [ "$dir" != "/" ]; do
  for f in "$dir/CLAUDE.md" "$dir/.claude/CLAUDE.md" "$dir/CLAUDE.local.md"; do
    [ -f "$f" ] && echo "$f"
  done
  dir=$(dirname "$dir")
done
# User-level
[ -f "$HOME/.claude/CLAUDE.md" ] && echo "$HOME/.claude/CLAUDE.md"
# Rules
find ./.claude/rules -name '*.md' 2>/dev/null
find "$HOME/.claude/rules" -name '*.md' 2>/dev/null
```

Read every file found. Don't skip — coherence audits depend on it.

## Step 2 — Audit (always run)

For every loaded file, report:

- **Line count** vs targets (≤ 200 Anthropic official, ≤ 100 Boris Cherny's own setup, ≤ 60 ideal practitioner consensus)
- **Approximate tokens** — heuristic: `wc -w FILE` (word count ≈ token count × 1.3), or `wc -c FILE / 4`
- **Instruction density** — count actionable rules (commands, constraints, conventions) vs filler (explanations, tutorials, commentary). Target: ≥ 70% actionable
- **Anti-pattern hits** — scan for each pattern in [Anti-patterns](#anti-patterns-to-scan-for) and quote the offending lines
- **Positional check** — are the most critical rules at the top or bottom? (primacy/recency bias: middle rules get less attention)
- **Phrasing check** — count negation-only rules ("don't X" without "do Y instead") and flag them for positive rewrites
- **Conflicts across files** — if two files give different rules for the same behavior, flag both with line numbers
- **Stale references** — paths or commands that don't exist on disk

Present the audit before any edit. The user should see the cost of the current state.

## Step 3 — Determine mode

After the audit, branch by what the user wants:

### Mode A — Create (target file does not exist)

1. Verify the parent directory exists; `mkdir -p` if needed.
2. Read manifest files in the project root to avoid duplicating their contents:
   - `package.json`, `Cargo.toml`, `go.mod`, `pyproject.toml`, `Gemfile`, `requirements.txt`
   - `Makefile`, `justfile`, `.github/workflows/*.yml` for command discovery
   - `.tool-versions`, `.nvmrc`, `.python-version` for runtime versions
   - `README.md` for project overview (don't repeat it)
3. Use `AskUserQuestion` for the **non-derivable** stuff:
   - Conventions that *differ* from language defaults
   - Commands the user runs daily that aren't obvious from the manifest
   - Gotchas / env vars / "never touch X" zones
   - Branch & PR conventions
4. Write the file using the [Minimal effective template](#minimal-effective-template). Skip any section that has nothing to say — empty sections are anti-patterns.

### Mode B — Update (target file exists)

1. Ask via `AskUserQuestion`: add a rule, remove a rule, prune for length, restructure, or apply audit suggestions.
2. **For additions**: state the trigger ("Claude got X wrong twice in this session") and verify the new rule passes the *"would removing this cause mistakes?"* test before writing.
3. **For removals**: explain *why* each removal is safe (covered by linter, derivable from code, etc.).
4. **For prunes**: rank by impact (delete first: code style, duplicates, vague rules, tutorial paragraphs) and ask which to apply.
5. **For restructures**: preserve substance, reorganize for scannability. Move critical rules to top and bottom.

### Mode C — Audit only (scope is `audit` or user asked for audit)

1. Present the full audit report from Step 2.
2. List specific suggestions ranked by impact — biggest token / clarity wins first.
3. Ask which to apply (default: none — audit is read-only unless the user opts in).
4. If the user approves changes, transition to Mode B for those changes.

## Step 4 — Apply changes

- Use `Edit` for surgical changes. Use `Write` only for full rewrites or new files.
- For every change, briefly state the rationale: *"deleting X — code style, use linter"*, *"adding Y — Claude got it wrong twice this session"*.
- If a removed rule is genuinely useful but path-scoped, suggest moving it to `.claude/rules/<topic>.md` with `paths:` frontmatter rather than deleting outright.

### Writing rules that stick

When adding or rewriting rules, apply these evidence-backed patterns:

- **Positive phrasing first**: "Use named exports" > "Don't use default exports". Flip negatives to positives where possible.
- **Include rationale**: "Never force push — rewrites shared history" outweighs bare "Never force push".
- **Specify failure modes**: "Always generate tests. If unclear: create a stub with TODO and stop. Do not skip."
- **Use standard header names**: `## Commands`, `## Conventions`, `## Gotchas` — Claude recognizes these from training.
- **Commands in code blocks**: Prose commands are suggestions; fenced commands are treated as executable.
- **Emphasis sparingly**: "IMPORTANT" or "YOU MUST" improves adherence but only if rare. If every rule is emphasized, none is.
- **Mermaid for workflows**: For multi-step processes with branching, Mermaid diagrams achieve 3-6x better token efficiency than prose. Use when a workflow has ≥ 5 steps with conditionals.

## Step 5 — Validate post-edit

After writing, re-check the target file:

- **Line count** — under target?
- **Specificity** — each rule concrete enough to verify? ("Use 2-space indentation" passes; "format properly" doesn't.)
- **Positioning** — critical rules at top and bottom?
- **Phrasing** — positive instructions where possible? Negations include an alternative?
- **Conflicts** — any new rule contradicts another loaded file?
- **Necessity** — every remaining rule passes the pruning test?
- **Sectional health** — no empty sections, no headers with nothing under them.

If any check fails, surface it to the user and offer to fix.

## Step 6 — Suggest follow-ups

After the edit, recommend next moves where applicable:

| Pattern in CLAUDE.md | Better home |
|---|---|
| Rule only relevant when touching `src/api/**` | `.claude/rules/api.md` with `paths:` glob |
| Multi-step procedure triggered by intent | Skill in `.claude/skills/<name>/SKILL.md` |
| Rule that needs deterministic enforcement | Hook in `.claude/settings.json` |
| Block tools / commands | `permissions.deny` in settings (or managed settings org-wide) |
| Personal preference shared across worktrees | `~/.claude/CLAUDE.md` (since `CLAUDE.local.md` is per-worktree) |
| Monorepo team-specific rules | Subdirectory CLAUDE.md (loads on demand) |
| Exclude other teams' rules | `claudeMdExcludes` in `.claude/settings.local.json` |
| Standard conventions Claude already follows | Delete — no home needed |

Recommend compound engineering if the user seems early in their CLAUDE.md journey: *"After this session, if Claude gets something wrong, ask it to update CLAUDE.md so it doesn't happen again. The file compounds in value over time."*

## Output

Report concisely:
- Files inspected (path + line/token count before/after)
- Changes applied with one-line rationale each
- Final line/token count vs target
- Instruction density (actionable rules / total lines)
- Suggested follow-ups (if any)

---

## Reference: the load hierarchy

Loaded at session start (concatenated, more specific wins on conflict):

1. **Managed policy** — `/Library/Application Support/ClaudeCode/CLAUDE.md` (mac), `/etc/claude-code/CLAUDE.md` (linux), `C:\Program Files\ClaudeCode\CLAUDE.md` (win) — cannot be excluded
2. **User** — `~/.claude/CLAUDE.md`
3. **Project** — `./CLAUDE.md` or `./.claude/CLAUDE.md`
4. **Local** — `./CLAUDE.local.md` (gitignored)
5. **Subdirectory** — loaded on demand when Claude reads files in that subtree

Plus: `.claude/rules/*.md` and `~/.claude/rules/*.md` — always loaded unless `paths:` frontmatter scopes them. After `/compact`, the project-root CLAUDE.md is re-injected; nested CLAUDE.md files are not re-injected until Claude accesses those directories again.

## Reference: include / exclude

| Include | Exclude |
|---|---|
| Bash commands Claude can't guess | Anything Claude can grep for |
| Conventions that **differ from defaults** | Standard language conventions |
| Required env vars and version constraints | Code style rules a linter would catch |
| Test commands and preferred runners | Long explanations or tutorials |
| Branch naming, PR conventions | File-by-file architecture |
| Architectural decisions with **rationale** | Frequently-changing info |
| Non-obvious gotchas (things Claude got wrong twice) | Persona assignments ("you are a senior engineer") |
| Compaction instructions (what to preserve) | Self-evident platitudes |

## Reference: length targets

| Source | Target | Notes |
|---|---|---|
| ETH Zurich study (Feb 2026) | As short as possible | Empty CLAUDE.md scored best for well-documented repos |
| Practitioner consensus | ≤ 60-100 lines | Sweet spot balancing coverage and adherence |
| Boris Cherny (Claude Code creator) | ~100 lines (~2,500 tokens) | His own personal setup |
| Anthropic official docs | ≤ 200 lines per file | Official ceiling |

Key finding: LLM-generated CLAUDE.md files (including `/init` output) **decreased success rates** and increased costs ~20% in the ETH Zurich study. Always review and prune auto-generated content.

## Reference: monorepo strategy

For monorepos, use the hierarchy to minimize context load:

```
monorepo/
├── CLAUDE.md               # Global conventions only (always loaded, ≤ 60 lines)
├── packages/
│   ├── api/CLAUDE.md        # API-specific (loads on demand)
│   ├── web/CLAUDE.md        # Web-specific (loads on demand)
│   └── shared/CLAUDE.md     # Shared package rules (loads on demand)
```

- Root file: only what applies across every package
- Package files: load lazily when Claude reads files in that directory
- Use `claudeMdExcludes` in `.claude/settings.local.json` to skip other teams' files
- Real-world result: one team reduced 47k words to 9k (-80%) with this pattern

## Anti-patterns to scan for

When auditing, flag any of these and quote the offending lines:

1. **Code style rules** — formatting, indentation, naming conventions → delete; use a linter
2. **Duplicated docs** — README contents, package.json scripts, architecture wiki dumps → delete or `@import` sparingly
3. **Vague rules** — "write good code", "use modern patterns", "be defensive" → delete or make specific
4. **Tutorial paragraphs** — multi-paragraph explanations → delete; link to docs
5. **File-by-file descriptions** — "src/foo handles X, src/bar handles Y" → delete; Claude can grep
6. **Tables of feature flags or config values** — token-heavy and stale fast → externalize
7. **Conflicting rules across files** — pick one, delete the other
8. **Auto-generated `/init` boilerplate** never refined → prune to actual project specifics
9. **Frontmatter or instructions for non-Claude tools** — move to `AGENTS.md`, then `@AGENTS.md` from CLAUDE.md
10. **Personal preferences in project CLAUDE.md** — move to `~/.claude/CLAUDE.md` or `CLAUDE.local.md`
11. **Empty sections** — headers with nothing meaningful underneath
12. **Stale references** — paths, commands, or files that no longer exist
13. **Negation-only rules without alternatives** — "Never use --legacy-peer-deps" without stating what to use instead
14. **Persona assignments** — "You are a meticulous senior engineer" → delete; specific rules outperform
15. **Every rule marked IMPORTANT** — when everything is critical, nothing is → reserve emphasis for ≤ 3 rules
16. **Large @imports** — imported files load at launch consuming full context; they help organization, not token budget

## Minimal effective template

For new project files:

```markdown
# [Project Name]

[One sentence: what this is and why it exists]

## Commands
- `cmd1` — what it does
- `cmd2` — what it does

## Conventions
[Only conventions that differ from language defaults. ≤ 5 rules.]

## Gotchas
[Required env vars, services that must run, version constraints, "never touch X" zones]
```

Skip any section with nothing to say. The `## Stack` section is usually redundant with manifest files — include only if non-obvious. The `## Architecture` section is usually redundant with directory listing — include only if the *why* behind the structure is non-obvious.

For new user files (`~/.claude/CLAUDE.md`):

Keep under 50 lines. Personal preferences only. No project-specific content. No code style rules.

## Important reminders

- **HTML comments are stripped** before injection (`<!-- maintainer notes -->`) — use them for human-only notes that shouldn't burn tokens. Comments inside code blocks are preserved.
- **`@imports` don't save context** — imported files load in full at launch (max 5 hops deep). They help organization, not token budget. For real conditional loading use `.claude/rules/` with `paths:` frontmatter.
- **`/memory`** in a session lists what's actually loaded. Use it to verify changes took effect.
- **`InstructionsLoaded` hook** logs which files load and why — useful for debugging path-scoped rules.
- **`AGENTS.md` interop**: Claude Code reads CLAUDE.md, not AGENTS.md. If a repo uses both, make CLAUDE.md `@AGENTS.md` so both tools see the same instructions.
- **Compaction**: project-root CLAUDE.md survives `/compact` (re-read from disk). Add a "Compact Instructions" section for rules that must persist across compaction if needed.
- **Compound engineering**: after a session where Claude made mistakes, ask it to update CLAUDE.md. The file compounds in value over time as it captures every past error.

## Hard prohibitions

- Never invent content that's supposedly in an existing CLAUDE.md — read the file first
- Never add a rule without showing the user *why* it earns its place
- Never delete a rule the user explicitly added without confirming
- Never add code style guidelines (use a linter)
- Never duplicate content from another file in the hierarchy — `@import` instead
- Never edit a managed-policy CLAUDE.md without explicit user confirmation (org-wide impact)
- Never write to `CLAUDE.local.md` without confirming the user wants the rule kept private to this worktree (vs. shared via project `CLAUDE.md` or user-global)
- Never add a negation-only rule without providing the alternative approach
