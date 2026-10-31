# Delegation guide

Reference for the `orchestrate` skill. Load this when the executor choice is non-obvious, a delegation prompt needs care, or the library review step needs a recipe.

## Delegation prompt template

Subagents and freshly-invoked skills have **no view of the current conversation**. A delegation that assumes shared context produces duplicated work, gaps, or the wrong output. Every delegation carries four things (Anthropic's orchestrator-worker spec):

1. **Objective** — the one concrete outcome this unit must produce. Not "look into X" — "determine whether X, and return the answer with evidence."
2. **Output format** — exactly what to return and how (a summary, a file at a path, a findings list, a patch). Reinforce it even when the agent knows its own format; it reduces drift.
3. **Tools and sources** — which tools, skills, files, or systems to use, and which to prefer.
4. **Boundaries** — what is in scope and, explicitly, what is out of scope, so parallel units don't overlap.

Also include, when relevant: file paths and short code excerpts showing the pattern to follow; condensed results from finished dependency units (not raw dumps); the branch-naming convention for coding work (`<user>/<task-id>-<short-desc>`); the role's model tier passed via the Agent call's `model` param; and the quality bar or acceptance criteria.

Ask executors to return **condensed summaries**, not raw logs or full file contents — this protects the orchestrator's context budget.

## Effort scaling

Match agent count to complexity. Over-spawning burns tokens; under-spawning serializes work that could run in parallel.

| Unit complexity | Agents | Notes |
|---|---|---|
| Simple fact-find / single discrete task | 1 | A few tool calls; don't fan out. |
| Direct comparison / moderate build | 2–4 | One angle or component each; clear non-overlapping boundaries. |
| Large, genuinely parallel investigation or build | 5+ | Only when the work truly divides; each with a distinct, well-bounded charge. |

Two levels of parallelism compound: run several units at once, and let each executor use its own tools in parallel. This is where the time savings come from — serial fan-out throws them away.

## Parallel vs sequential

- **Parallel** when units share no data dependency. Issue the Agent calls (and independent skill invocations) in a single turn.
- **Sequential** only when one unit needs another's output. Wait for the dependency, condense its result, and pass it into the next delegation.
- **Overlap** review and dispatch: start reviewing a finished unit while the next unit's agent is still running.

## Executor selection

Prefer the most specific executor that fits.

- **Dedicated orchestrator skills** — for whole sub-workflows: `tech-lead` (implement a plan across developer + reviewer agents), `research` (fan-out external research), an installed internal-investigation skill (internal claim verification and root cause across code, config, data, observability and docs). Route the whole sub-workflow to these; do not hand-roll their internals.
- **Worker agents** — for one scoped unit each: `developer` (a coding task in a worktree), `reviewer` (quality-gate a worktree), the `*-researcher` agents (a research subtopic), any internal per-domain researcher agents that are listed, `Explore` (broad read-only code search), `Plan` (design a strategy), `general-purpose` (anything without a better fit).
- **Generator / utility skills** - for structured output: `draw-diagram`, `write-ticket`, `bilbo:note`, and the like.
- **Gateway skills** — for reaching external systems: whichever installed skills front Slack, Google Workspace, Jira, Grafana, code search and the like.

Discover the live inventory from the available-skills and available-agents lists in context; the names above are common choices, not the full set.

## Library review recipe

The review gate in Step 5 splits by unit type. Code units go to the `review` skill (bare review-tier model token) — do not hand-roll a code review here. The recipe below is for NON-code units, run by a review-tier agent, grounding "is this correct?" in the team's own documents.

1. **Pick by review dimension:**
   - **Project / business direction** → ask whether the output matches the requirements, scope, and decisions on record.
2. **Query** `bilbo:reference` with a focused question ("requirements for X"), read its cited answer, and check the artifact against it.
3. **Fold the findings** into your direction assessment. Treat library output as evidence, not gospel — cross-check against the acceptance criteria.
4. **Fail gracefully.** If `bilbo:reference` finds no library source, skip the library review, note it was skipped, and proceed on the other checks. Never fabricate a review.

## Retry and escalation

- **Retry limit:** ~2 per unit. Re-delegate with specific corrective feedback drawn from the review — not a vague "try again."
- **Escalate to the user** when: direction is wrong (not just imperfect), a decision fork is genuinely theirs, or a unit has failed twice. Present full context and the concrete choice or blocker.
- **Report, don't loop.** Continued retries past the limit rarely converge without human judgment and waste tokens.
