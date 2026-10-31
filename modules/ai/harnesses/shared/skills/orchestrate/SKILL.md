---
name: orchestrate
description: Decomposes multi-domain work, delegates to subagents and skills, reviews results. Use for "orchestrate this". NOT for a plan (tech-lead) or research (research).
argument-hint: "[goal] [model or plan=/work=/review= overrides]"
allowed-tools:
  - Agent
  - Skill
  - AskUserQuestion
  - TaskCreate
  - TaskUpdate
  - TaskList
  - Read
  - Grep
  - Glob
  - Bash(git:*)
  - Bash(ls:*)
---

# Orchestrate

## Goal

Drive a complex goal to completion by coordinating other agents and skills — never by doing the hands-on work directly. Decompose the goal, route each unit of work to the best executor in hand, run independent work in parallel, verify direction after each step, check in with the user at real decision points, and synthesize the results into a coherent whole. Reading code or outputs to verify alignment is fine; producing the deliverable is not — that is delegated. Staying at the coordination layer keeps the orchestrator's context focused on the map instead of filling with implementation detail.

## When NOT to use this skill

- A single-step task, quick question, or single-file edit — do it directly.
- Purely implementing a known plan — use `tech-lead`.
- Purely external research — use `research`.
- Purely internal investigation, when an installed skill covers it — use that skill.

## Operating model

Four principles govern every decision below:

1. **Orchestrate, don't execute.** Substantive work — writing code, running research, drafting documents, querying systems — goes to a subagent or a skill. You may handle a trivial one-off step directly (a single read, an `ls`, a `git status`) when spawning an agent would cost more than it saves. Anything beyond trivial gets delegated.
2. **Compose, don't reimplement.** When a task fits a dedicated orchestrator or skill you already have, route to it — do not hand-roll its workflow. See the routing table below.
3. **Check in on purpose.** Stop and ask the user at genuine decision forks, when a knowledge gap blocks good delegation, or when direction drifts. Quiz the user to fill gaps; ask for their opinion when the call is really theirs.
4. **Ground direction in knowledge.** Before and during the work, consult the sources that pin down "correct": bilbo's notes through `bilbo:recall` (decisions, plans and gotchas), its library sources through `bilbo:reference` (code style, project and business standards), and repo conventions. Do not delegate against assumptions you could have verified.

## Model tiers

Every run has three roles, each on its own model tier. Parse overrides from `$ARGUMENTS` before anything else: a bare model token (`opus` | `sonnet` | `haiku` on Claude Code, a model id the running harness accepts elsewhere; a Fable model is refused) sets all three roles; `plan=<model>`, `work=<model>`, `review=<model>` set one role each; later tokens win; an unknown role or model gets a one-line correction, not a guess. The same grammar drives the `review` skill, so the two surfaces stay interchangeable.

| Role | Who runs on it | Default |
|---|---|---|
| `plan` | the planning agent (Step 2) | `opus` |
| `work` | implementation/worker agents (Step 4) | `sonnet` |
| `review` | the review stage (Step 5) | the harness's high-reasoning model (`opus` on Claude Code, `gpt-6-astra` high on Codex, `pro` on agy, which `review` accepts; the model behind it is gemini-4-argon-high) |

Strong model to plan and to judge, cheaper model to produce — the validated split for orchestrated work. Pass the tier in each Agent call's `model` param. Skills invoked via the Skill tool run in this session (no model param): when routing a unit to `tech-lead` or another orchestrator skill, state the work tier in its invocation arguments so it passes the model on to the agents it spawns; when invoking `review`, pass the review tier as a bare model token.

## Workflow

### Step 0 — Confirm orchestration is the right mode

Because this skill can auto-trigger, first check that the task actually warrants orchestration.

- **Too small?** A single-step task, a quick question, or a one-file edit does not need orchestration. Say so and do it directly (or hand it back), rather than spinning up a multi-agent flow.
- **Fits a dedicated orchestrator exactly?** If the task is *purely* implementing a known plan, route to `tech-lead`. If it is *purely* external research, route to `research`. If it is *purely* internal investigation and an installed skill covers it, route to that skill. In these clean cases, invoke that skill instead of duplicating its logic here.
- **Genuinely multi-part / multi-domain?** Proceed with the full workflow.

### Step 1 — Understand the goal

Establish what "done" means before planning anything.

- Parse `$ARGUMENTS` and the conversation for the goal, constraints, and definition of done.
- If the goal is ambiguous or under-specified, ask 2–4 crisp questions with `AskUserQuestion`. Quiz the user to surface constraints they assume but haven't stated (deadlines, quality bar, systems in play, what to avoid).
- Ground the direction: find the relevant notes through `bilbo:recall`, the standards through `bilbo:reference`, and the repo conventions that define correctness for this goal. Note which notes cover **project/business** direction; that is what Step 5 checks scope and intent against. Code-style references need no attention here: the `review` skill finds those itself from the diff.

Do not over-interview. Extract scope and the quality bar; the decomposition handles precision.

### Step 2 — Map the work to executors

Delegate decomposition to a dedicated planning agent: spawn a `Plan` agent on the **plan tier** model with a self-contained prompt carrying the goal, constraints, definition of done, and the grounding notes from Step 1. Instruct it to ground the plan in the library the way the `review` skill does: one `bilbo:reference` skill call per concern, and cite what it used (`bilbo:<id>#<heading> "<quote>"`) in the plan, never inventing coverage when no library source fits. The agent returns the unit map; validate it against the goal, adjust executor choices yourself, and own the final routing using the table below. For each unit record:

- **What** — a clear description and acceptance criteria.
- **Executor** — the skill or agent that will do it.
- **Dependencies** — which units must finish first (use IDs T1, T2, …).
- **Parallelism** — group independent units to run together; sequence dependent ones.

Scale effort to complexity — do not over-spawn. Rough heuristic: one agent for a simple unit, 2–4 for a comparison or a moderate build, more only for genuinely large parallel work. Detailed heuristics and executor-selection guidance live in `{baseDir}/references/delegation-guide.md` — read it when the choice is non-obvious.

### Step 3 — Present the plan and get approval

Show the user the decomposition: each unit, its chosen executor, dependencies, and the parallel/sequential order. Wait for approval before spawning — misaligned decomposition wastes all downstream work and tokens, so this gate is worth the pause.

Create a task list with `TaskCreate` (one task per unit) so progress is visible and you can track status as agents return. Set dependencies with `TaskUpdate`.

### Step 4 — Delegate

Dispatch the approved work.

- **Self-contained prompts.** Subagents and freshly-invoked skills start with no view of this conversation. Every delegation must carry its own objective, the output format you expect, the tools/sources to use, clear boundaries, and any file paths, code excerpts, patterns, and condensed results from finished dependencies. See the delegation template in the reference file.
- **Parallel by default.** Issue independent Agent calls (and independent skill invocations) in the same turn. Sequence only real dependencies.
- **Work tier by default.** Pass the work-tier model in each Agent call's `model` param; a unit routed to a skill instead notes the tier in the invocation arguments (see Model tiers).
- **Mark tasks in_progress** with `TaskUpdate` as you dispatch.

### Step 5 — Review and verify direction

As each unit returns, verify **intent, not just completion** — a unit that "finished" but solved the wrong problem is worse than one that failed cleanly.

- Check the result against the acceptance criteria and against integration with sibling units.
- If a summary is vague or raises doubt, read the key output files directly (read-only).
- **Code units** - invoke the `review` skill (deep multi-agent review grounded in library sources), passing the review tier as a bare model token and an explicit `<base>...<branch>` target whenever the unit was implemented on a branch or in a worktree (the `developer` agent reports its branch; the convention is `<user>/<task-id>-<short-desc>`). The target is not optional there: your cwd cannot see a worktree's changes, so left to its own resolution `review` reads this tree - clean, so it stops on an empty diff or reviews the wrong work. Worktrees share the repo's refs, so a range resolves from anywhere in it. Fall back to `review`'s default target resolution only when the work happened in your own working tree. Its Verdict line is the gate: confirmed findings feed Step 6. When the unit should also be committed and pushed, route to a `reviewer` agent or `review-and-push --no-fix --base=<merge base of the default branch and HEAD>` instead (pass the base whenever HEAD is ahead, so committed branch work is gated): the gate delegates to `review` internally, and Step 6 owns re-delegation, so the gate must not fix; its `BLOCKED` or `FIXED_DECLINED` Gate line feeds Step 6 like a Verdict line.
- **Non-code units** - spawn one review agent on the review tier following the same shape as `review`: ground in what one `bilbo:reference` skill call per concern returns, require evidence for every finding with its grounding labeled (`bilbo:` citation, web URL, or judgment), separate confirmed from unverified claims, and skip gracefully with a stated gap when no library source fits - never fabricate a review.
- Update task status with `TaskUpdate`.

### Step 6 — Course-correct or escalate

- **Minor drift:** re-delegate with specific corrective feedback (counts toward a retry limit of ~2 per unit).
- **Wrong direction, or a fork that is the user's call:** stop and check in — present the situation and ask for a decision or opinion.
- **Failed twice:** stop and report with full context. Continued retries rarely converge without human judgment.

### Step 7 — Synthesize and hand off

When all units are complete or blocked:

- **Synthesize, don't relay.** Integrate the results into one coherent outcome; do not paste raw agent dumps. Cross-reference where units inform each other.
- Report each unit's status, any deviations from the plan, and open follow-ups.
- Offer to persist the outcome if apt: route to `bilbo:note` rather than writing files directly.

## Choosing an executor

Route each unit to the most specific option that fits. Discover the current inventory from the available-skills and available-agents lists in context — this table names common choices, not an exhaustive set.

| Task shape | Route to |
|---|---|
| Implement a multi-task plan (coding) | `tech-lead` skill |
| Deep external / general research | `research` skill |
| Internal claim verification or root cause (code, config, data, observability, docs), when an installed skill covers it | that skill |
| One internal domain explored without a claim ledger | the matching internal per-domain researcher agent, if one is listed |
| One discrete coding task | `developer` agent (worktree) |
| Quality-gate code before merge | `reviewer` agent or `review-and-push --no-fix` skill |
| Deep code-quality review, no push | `review` skill (pass the review tier as a bare model token) |
| Broad read-only search across many files | `Explore` agent |
| Design an implementation strategy | `Plan` agent |
| Produce a diagram / ticket / note | `draw-diagram`, `write-ticket`, `bilbo:note` skills |
| Reach an external system (Slack, Jira, Sheets, Grafana, …) | the matching installed gateway skill, if one is listed |
| No better fit | `general-purpose` agent |

## Checking in with the user

Checking in is a first-class part of the job, not an interruption. At a balanced cadence:

- **Gate at the plan** (Step 3) — always.
- **Pause at major decision forks** — when two reasonable paths exist and the choice shapes the outcome, present them and ask.
- **Quiz to close gaps** — when you cannot write a good delegation prompt without information only the user has, ask before delegating on a guess.
- **Ask for opinions** — when the call is genuinely the user's (taste, priority, risk tolerance), surface it rather than deciding silently.
- Otherwise, keep running. Do not confirm every phase — that is high-touch noise the user didn't ask for.

## Key behaviors

- **Coordination over execution.** Delegate substantive work; keep only trivial one-off inspection in-band.
- **Compose over reimplement.** Route to the dedicated orchestrator or skill when the task fits it.
- **Parallel by default.** Overlap independent work; overlap review of finished units with dispatch of pending ones.
- **Self-contained delegation.** Every prompt carries all context the executor needs; ask executors to return condensed summaries, not raw logs, to protect the orchestrator's context budget.
- **Verify intent, not completion.** Read key outputs directly when a summary is unclear.
- **Escalate on repeated failure.** Two failed retries on a unit means stop and report.

## Failure modes

- **A subagent fails or returns nothing.** Mark its task blocked, keep independent units running, and re-delegate once with a tighter prompt. If it fails again, present partial results and escalate — a stalled unit should not freeze the whole run.
- **The user rejects the plan (Step 3).** Do not spawn anything. Ask what to change — scope, decomposition, executors, or order — and re-present. A rejected plan is far cheaper to redo than misdirected parallel work.
- **A result comes back off-track.** Handle it in Step 5/6: re-delegate with specific feedback or escalate. Never record a wrong-direction result as success.
- **No library source covers the unit at the review gate.** For non-code units, skip the library check and note that it was skipped. For code units, `review` runs ungrounded and labels it - carry that label into your report. Either way the workflow must not block, and the findings must never be invented.
- **No executor fits a unit.** Route to the `general-purpose` agent, or ask the user how to proceed — guessing at an executor wastes a delegation.

## Hard prohibitions

- Never produce the deliverable directly — code, documents, research legwork, and system queries all get delegated, because staying at the coordination layer keeps the orchestrator's context on the map instead of implementation detail. The only exception is a trivial one-off inspection step.
- Never reimplement a dedicated orchestrator's workflow (`tech-lead`, `research`, an installed investigation skill) when routing to it would do — hand-rolled copies drift from the maintained version.
- Never spawn agents or invoke work skills before the plan is approved (Step 3), because a misread scope multiplied across parallel subagents burns far more tokens than a single agent would.
- Never relay raw agent output as the final result — synthesize it for the user's actual question (Step 7); raw dumps are disconnected and repetitive.
- Never fabricate library review feedback; if no library source covers it, say the review was skipped, because an invented review is worse than a missing one.
- Never fire the full workflow for a trivial single-step task — orchestration overhead on small work is pure waste; do it directly instead.

If a situation arises that this workflow does not cover, read `{baseDir}/references/delegation-guide.md` for detailed delegation and escalation guidance.
