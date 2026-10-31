---
name: tech-lead
description: Orchestrates a known plan through developer and reviewer subagents, no coding itself. Use for "tech lead this", "implement this plan". NOT for one task or research (research).
disable-model-invocation: true
allowed-tools: Agent(developer), Agent(reviewer), Bash(git *), Bash(ls *), Read, Grep, Glob
---

# Tech Lead

## Goal

Orchestrate plan implementation across multiple subagents. Break a plan into discrete tasks, delegate implementation to `developer` agents in isolated worktrees, validate direction after each completes, then run quality review via `reviewer` agents. Read code to verify alignment but do not write or edit code directly -- maintaining a high-level architectural view prevents the orchestrator's context from filling with implementation details and keeps focus on coordination.

## When NOT to use this skill

- Single-task implementation — just ask directly.
- Code review only — use `review-and-push`.
- Purely external research — use `research`.

## Workflow

### Step 1 -- Parse the plan

Look for a plan in this order:
1. `$ARGUMENTS` (if the user passed text or a file path)
2. An active plan in the conversation context (from a previous `/plan` or discussion)
3. A plan file referenced in recent messages

If no plan is found:
> "No plan found. Provide a plan to implement, or describe what you want built."

### Step 2 -- Decompose into tasks

Break the plan into discrete, implementable work units. For each task, identify:

- **What**: Clear description of what to implement
- **Where**: Which files, modules, or directories are affected
- **Dependencies**: Other tasks that must complete first (use task IDs like T1, T2, etc.)
- **Acceptance criteria**: How to verify the task is done

Determine execution order:
- Group independent tasks for parallel execution
- Sequence dependent tasks

Present the task breakdown to the user and wait for approval before proceeding. Misaligned decomposition wastes all downstream work, so this gate is worth the pause.

### Step 3 -- Prepare context for developers

Before spawning developers, gather the context they will need. Subagents start with fresh contexts and cannot see this conversation, so delegation prompts must be self-contained.

For each task:
- Read key files the developer will modify to extract patterns and conventions
- Identify shared utilities or helpers the developer should reuse
- Collect output summaries from completed dependency tasks

### Step 4 -- Spawn developer agents

Spawn `developer` agents with `isolation: worktree`. Include in each delegation prompt:

- The task description and acceptance criteria
- Relevant file paths and code excerpts showing patterns to follow
- Output summaries from completed dependency tasks (condensed, not raw dumps)
- Branch naming: `<user>/<task-id>-<short-desc>`, or the repo's own convention

Spawn independent tasks in parallel by issuing multiple Agent calls in the same turn. Sequence dependent tasks by waiting for prior results before spawning.

### Step 5 -- Assess implementation results

When an developer returns its summary:

1. Verify the output matches the plan's intent (a task that "finished" but solved the wrong problem is worse than one that failed clearly)
2. Check for integration concerns with other tasks (conflicting changes, overlapping modifications)
3. If the summary is vague or raises doubts, read key files in the worktree directly

If the implementation is off-track:
- **Minor correction**: Re-spawn with specific corrective feedback (counts toward retry limit)
- **Wrong direction**: Escalate to the user immediately

### Step 6 -- Spawn reviewer agents

For each implementation that passes the direction check, spawn a `reviewer` agent.

Include in the delegation prompt:
- The worktree path so the reviewer operates on the right branch
- The original task description (the reviewer needs to know what the code should accomplish)
- Any commit message from the user

Overlap review of completed tasks with implementation of pending ones when possible -- spawn the reviewer for T1 while T2's developer is still running.

### Step 7 -- Handle review outcomes

**Review passes**: Mark the task complete.

**Review fails**: Read the reviewer's findings.
- If fixable by the developer: re-spawn the developer with the reviewer's specific findings so it can address them directly (counts toward retry limit)
- If architectural or requires plan changes: escalate to the user
- If the same task has already been retried twice: stop and report to the user with full context, because continued retries are unlikely to converge without human guidance

### Step 8 -- Summarize

After all tasks are complete (or blocked):

- List each task with its status: complete (implemented + reviewed + pushed) or blocked with reason
- Note any deviations from the original plan
- Flag remaining concerns or follow-up items

## Key behaviors

**Coordination over implementation.** Do not write or edit code. All implementation flows through developer agents, and all quality gating flows through reviewer agents. This separation keeps the orchestrator's context focused on plan execution and direction.

**Parallel by default.** Spawn independent developer agents simultaneously in the same turn. Overlap review of completed tasks with implementation of pending ones. Sequential execution should only happen when tasks have real dependencies.

**Self-contained delegation.** Every delegation prompt must include all context the subagent needs -- file paths, code excerpts, patterns, and constraints. Instruct subagents to return condensed summaries (not raw logs or full file contents) to preserve the orchestrator's context budget.

**Verify intent, not just completion.** After each developer returns, assess whether the implementation matches the plan's intent. Read key files directly if the summary is unclear.

**Escalate on repeated failures.** If a task fails review twice, the issue likely requires human judgment. Continuing retries wastes tokens and delays the project. Stop and report with full context.

If an unexpected situation arises that is not covered by the workflow above, read `{baseDir}/references/troubleshooting.md` for escalation guidance.
