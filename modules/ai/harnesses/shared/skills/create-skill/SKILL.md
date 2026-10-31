---
name: create-skill
description: Interviews requirements and generates a SKILL.md. Use for create/build a skill. NOT for agents (create-agent) or CLAUDE.md (edit-claude-md).
argument-hint: "[skill name or description]"
allowed-tools: Bash(ls *), Bash(cat *), Bash(find *), Bash(wc *), Bash(mkdir *), Bash(test *), Bash(rg *), Read, Write, Edit, Glob, Grep, AskUserQuestion, Skill(bilbo:recall), Skill(bilbo:reference)
---

# Create Skill

Generate a production-quality Claude Code skill through guided requirements gathering, structured generation, and library-powered review.

## When NOT to use this skill

- **Creating an agent** rather than a skill — use `create-agent` instead.
- **Editing an existing skill** — this skill is for generating a new SKILL.md from scratch, not revising one already in place.
- **Non-skill automation** — hooks, `.claude/rules/`, or CLAUDE.md files are not skills; for CLAUDE.md use `edit-claude-md`.

DO NOT start generating the skill until the interview phase is complete. Gathering requirements first prevents rework and produces skills that actually trigger correctly.

## Phase 1 — Gather requirements

If `$ARGUMENTS` provides a topic or description, use it as the starting point. Extract as much as possible from the conversation history (the user may have just done the workflow they want to turn into a skill).

Ask the user to clarify anything ambiguous. Use `AskUserQuestion` to keep the interview structured. Gather:

### 1a — Intent

- **What should this skill enable Claude to do?** Get a concrete answer, not "help with X".
- **What triggers it?** Specific phrases a user would say, file types, contexts.
- **What is the expected output?** A file, a report, a transformation, an action, a conversation.
- **Should Claude trigger this autonomously, or only when the user types the command?** Side effects (deploy, commit, send message) should be manual-only (`disable-model-invocation: true`).

### 1b — Workflow

- **What are the steps?** Walk through the workflow from start to finish. If the user just did this workflow in the current session, extract the steps from conversation history.
- **Are there decision points or branches?** Different paths based on input type, user choice, or environment.
- **Are there validation gates?** Steps where output must be verified before proceeding.
- **Are there dependencies?** Tools, MCP servers, CLI commands, libraries, APIs the skill needs.

### 1c — Scope and boundaries

- **What should this skill NOT do?** Negative triggers prevent false positives.
- **Where should the skill live?** Common (all machines), personal (personal only). Default to common unless it is clearly machine-specific.
- **Should it accept arguments?** If so, what kind (file path, topic, flags)?

If the user gave enough context in `$ARGUMENTS` or conversation history to answer most of these, fill in the answers yourself and confirm with a brief summary rather than asking each question individually. Adapt to the user's pace — do not over-interview.

## Phase 2 — Generate the skill

### 2a — Determine the directory

Resolve the target path based on the scope from Phase 1:

| Scope | Path |
|---|---|
| common | `<tier>/skills/<skill-name>/` in the repo that provides the skill set, in its shared tier |
| personal | the same path in its machine-specific tier |

If running outside the repo that provides the skill set, use `.claude/skills/<skill-name>/` relative to the project root.

Check that the directory does not already exist. If it does, ask the user whether to overwrite or pick a different name.

### 2b — Choose the skill pattern

Based on the gathered requirements, select the primary pattern:

| Pattern | Use when |
|---|---|
| **Tool Wrapper** | The skill packages conventions or best practices for a library/tool/framework as on-demand knowledge |
| **Generator** | The skill produces structured output (documents, configs, code) from a template + style guide |
| **Reviewer** | The skill evaluates artifacts against a checklist, producing a scored findings report |
| **Inversion (Wizard)** | The skill interviews the user through phases before producing output |
| **Pipeline** | The skill enforces a strict multi-step workflow with validation gates between steps |

Many skills combine patterns. A skill-creator (this one) combines Inversion + Generator + Reviewer.

### 2c — Write the frontmatter

Generate the YAML frontmatter:

- **`name`**: kebab-case, matches directory name, max 64 chars
- **`description`**: Under 1024 characters. Must state BOTH what the skill does AND when to use it. Include natural-language trigger phrases. Include negative triggers if scope could be ambiguous. Lean slightly "pushy" — Claude tends to under-trigger, so the description should encourage activation when relevant.
- **`argument-hint`**: Set if the skill accepts arguments. Use bracket notation: `[topic]`, `[file path]`, `[issue-number]`.
- **`allowed-tools`**: Only the tools the skill actually needs. Scope Bash permissions with glob patterns (e.g., `Bash(git:*)` not `Bash(*)`).
- **`disable-model-invocation`**: Set to `true` for skills with side effects (deploy, commit, send, delete).
- **`model`**: Only set if the skill genuinely needs a specific model (e.g., opus for complex reasoning).

### 2d — Write the body

Structure the SKILL.md body following these rules:

1. **Open with a one-sentence goal** — what happens when this skill runs.
2. **Use imperative language** — "Read the file", "Generate a report", not "You should read the file".
3. **Step-by-step instructions** — numbered phases with clear actions at each step.
4. **Explain the *why* behind constraints** — "Keep under 500 lines because once loaded, every token competes with conversation history" is stronger than "MUST keep under 500 lines".
5. **Include concrete examples** where the output format matters.
6. **Add a Hard prohibitions section** at the end for true guardrails.
7. **Keep under 500 lines.** If approaching this limit, move reference material to `references/` and detailed templates to `assets/`.

### 2e — Create supporting files if needed

- **`references/`**: Checklists, style guides, API specs the skill loads on demand.
- **`assets/`**: Templates, boilerplate files referenced by path (not loaded into context).
- **`scripts/`**: Executable code for deterministic operations. Include install commands for dependencies.

Reference all supporting files from SKILL.md with clear guidance on when to load each one.

### 2f — Write the files

Create the directory structure and write all files. Use `Write` for new files.

## Phase 3 — Self-review

Before showing the skill to the user, read the quality checklist and verify the generated skill against it.

```
Read references/quality-checklist.md from this skill's directory
```

Walk through each item. Fix any failures silently — do not present a skill that fails its own checklist.

Count the SKILL.md body lines. If over 500, refactor: move reference material to `references/`, templates to `assets/`, deterministic logic to `scripts/`.

## Phase 4 — Library review

Invoke the `bilbo:reference` skill to find the library sources on skill authoring best practices, and critique the generated skill against its answer.

### 4a — Submit for review

Invoke `bilbo:reference` with a query naming the topic (skill authoring best practices). Read its cited answer, then review the full generated SKILL.md against it with this review question:

> "Review this skill for quality, best practices compliance, and potential issues. Check: frontmatter quality (name, description, triggers), body structure (progressive disclosure, conciseness, imperative language), anti-patterns (kitchen sink, vague descriptions, heavy-handed MUSTs, missing dependencies). Here is the skill: [full SKILL.md content]"

### 4b — Present results

Show the user:
1. The generated skill (full SKILL.md and any supporting files).
2. The library review findings.
3. Any changes you recommend based on the review.

Ask the user which library suggestions to incorporate.

### 4c — Apply feedback

Revise the skill based on user decisions and library feedback. Re-run the self-review checklist after changes.

### 4d — Library miss protocol

If `bilbo:reference` finds no library source on the topic, say so, note that the review was skipped and proceed on judgment - there is no external fallback to retry. The generated skill is still valid - only the library review step is blocked.

## Phase 5 — Finalize

After the user approves:

1. Confirm all files are written to disk.
2. Run `wc -l` on the SKILL.md to report final line count.
3. Wire it up: switch the host from the repo that provides the skill set (or tell the user to). Phase 2 wrote the skill into that repo's source tree; a NEW skill is not linked into `~/.claude` or `~/.codex` until a switch, because the farm is enumerated from the store copy.

## Output

Report concisely:
- Skill path and file list
- SKILL.md line count
- Pattern(s) used
- Library review summary (if performed)
- How to invoke: `/<skill-name>`

No congratulations, no filler, no summary of what you did.

## Hard prohibitions

- Never generate a skill without gathering requirements first (Phase 1). Jumping straight to generation produces vague descriptions and missed edge cases.
- Never write a `description` field without specific trigger phrases. "Helps with X" guarantees missed triggers.
- Never put XML angle brackets in frontmatter fields. They pose prompt-injection risks.
- Never exceed 500 lines in SKILL.md without refactoring into supporting files.
- Never hardcode absolute paths. Use paths relative to the skill directory.
- Never list all available tools in `allowed-tools`. Only what the skill needs.
- Never skip the self-review checklist (Phase 3). Catching issues before the user sees them is the whole point.
- Never loop when `bilbo:reference` finds no library source for this topic - accept it and proceed, noting the gap.
- Never fabricate library review feedback. If the review was not performed, say so.
