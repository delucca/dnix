---
name: create-agent
description: Interviews requirements and generates an AGENT.md. Use for create/build an agent. NOT for skills (create-skill) or CLAUDE.md (edit-claude-md).
argument-hint: "[agent name or description]"
allowed-tools: Bash(ls *), Bash(cat *), Bash(find *), Bash(wc *), Bash(mkdir *), Bash(test *), Bash(rg *), Read, Write, Edit, Glob, Grep, AskUserQuestion, Skill(bilbo:recall), Skill(bilbo:reference)
---

# Create Agent

Generate a production-quality Claude Code agent definition through guided requirements gathering, structured generation, and library-powered review against agent architecture best practices.

## When NOT to use this skill

- **Creating a skill** rather than an agent — use `create-skill` instead.
- **Editing an existing agent definition** — this skill is for generating a new AGENT.md from scratch, not revising one already in place.
- **Writing or editing CLAUDE.md files** — use `edit-claude-md` instead.

DO NOT start generating the agent until the interview phase is complete. Agents that ship without clear responsibility boundaries, tool constraints, and delegation protocols produce unreliable behavior and waste token budgets.

## Phase 1 — Gather requirements

If `$ARGUMENTS` provides a topic or description, use it as the starting point. Extract as much as possible from the conversation history (the user may have described what they need the agent to do).

Ask the user to clarify anything ambiguous. Use `AskUserQuestion` to keep the interview structured. Gather:

### 1a — Purpose and responsibility

- **What is this agent's single responsibility?** Agents that try to do multiple things become unreliable. Push for a focused, one-sentence purpose. "Implement code changes" is good. "Implement, review, and deploy code" is three agents.
- **Who spawns this agent?** Orchestrator agents (like tech-lead), skills, or the user directly?
- **What does the agent receive as input?** Task descriptions, file paths, context summaries, data payloads.
- **What does the agent return?** Condensed summary, structured report, file modifications, status codes.

### 1b — Architecture pattern

- **What pattern does this agent follow?** Help the user pick:
  - **ReAct**: Observe-reason-act loop. Good for tool-heavy, single-domain tasks with dynamic adaptation. Token-heavy.
  - **Plan-and-Execute**: Generate plan upfront, execute sequentially. Faster, predictable costs, but brittle if the environment changes mid-execution.
  - **Evaluator-Optimizer**: Generate-then-critique loop. Good when clear evaluation criteria exist and iterative refinement adds value.
  - **Worker**: Receives delegated subtasks from an orchestrator. Focused execution, returns condensed results.
  - **Orchestrator**: Decomposes tasks and delegates to worker agents. Reads code to verify direction but never writes code directly.
- **Does this agent interact with other agents?** If so, document the delegation protocol: what context to pass, what format for summaries, and how errors propagate.

### 1c — Tools and capabilities

- **What tools does the agent need?** List the minimum set. Each additional tool increases cognitive overhead and selection ambiguity. Prefer "one agent, one tool" when possible. Common tools:
  - `Bash` — with scoped glob patterns (`Bash(git *)`, not `Bash(*)`)
  - `Read`, `Write`, `Edit` — file operations
  - `Grep`, `Glob` — search
  - `Skill` — to invoke existing skills
  - `Agent` — to spawn subagents (orchestrators only)
  - MCP tools — scoped with glob patterns
- **What model should it use?** Default to `sonnet` unless the task genuinely needs complex reasoning (`opus`). Consider `haiku` for high-volume, simple tasks.
- **What effort level?** `low`, `medium`, `high`, or `xhigh`. Match to task complexity.
- **Does it need isolation?** `worktree` for agents that modify files (prevents conflicts with other agents). Not needed for read-only agents.

### 1d — Error handling and guardrails

- **What should happen when the agent fails?** Return structured error report? Retry with adjusted parameters? Escalate to a human or orchestrator?
- **Are there hard boundaries?** Maximum retries, tool-call caps, time limits, off-limits actions.
- **Does the agent perform high-risk actions?** Actions that are irreversible, affect shared state, or have financial impact should require human approval or orchestrator confirmation before execution.

### 1e — Scope and placement

- **Where should this agent live?** Common (all machines), personal (personal only). Default to common unless clearly machine-specific.

If the user gave enough context in `$ARGUMENTS` or conversation history to answer most of these, fill in the answers yourself and confirm with a brief summary rather than asking each question individually. Adapt to the user's pace.

## Phase 2 — Generate the agent

### 2a — Determine the file path

Resolve the target path based on the scope from Phase 1:

| Scope | Path |
|---|---|
| common | `<tier>/agents/<agent-name>.md` in the repo that provides the agent set, in its shared tier |
| personal | the same path in its machine-specific tier |

If running outside the repo that provides the agent set, use `.claude/agents/<agent-name>.md` relative to the project root.

Check that the file does not already exist. If it does, ask the user whether to overwrite or pick a different name.

### 2b — Write the frontmatter

Generate the YAML frontmatter:

- **`name`**: kebab-case, matches the file name (minus `.md`), max 64 chars
- **`description`**: Under 1024 characters. State what the agent does, who spawns it, and when to use it. Include `Use proactively whenever...` if it should be auto-triggered by orchestrators. Include negative triggers if the scope could be ambiguous.
- **`tools`**: List only the tools the agent actually needs. Scope Bash permissions with glob patterns.
- **`model`**: `opus`, `sonnet`, or `haiku`. Match to task complexity.
- **`effort`**: `low`, `medium`, `high`, or `xhigh`. Match to reasoning depth needed.
- **`isolation`**: Set to `worktree` if the agent modifies files.

### 2c — Write the body

Structure the AGENT.md body:

1. **Open with a one-sentence purpose** — what this agent does and what it returns.
2. **Workflow section** — numbered steps with clear actions at each step. Each step should:
   - State what to do (imperative language: "Read the file", "Run the tests")
   - Explain what to pass downstream or return upstream
   - Define gate conditions where the agent must verify before proceeding
3. **Key behaviors section** — 3-5 bullet points covering:
   - Scope discipline (stay focused, do not expand beyond the assigned task)
   - Pattern adherence (follow existing conventions)
   - Error handling (what to do when things fail)
   - Summary format (condensed output for orchestrator context budgets)
   - Decision-making stance (decide and document vs. block and ask)

Follow these writing principles:
- **Imperative language** — "Analyze the code", not "You should analyze the code"
- **Explain the *why* behind constraints** — "Return condensed summaries because the orchestrator's context budget is limited" beats "ALWAYS keep summaries short"
- **Concrete examples** where the output format matters — show the exact structure the agent should return
- **Positive phrasing** — "Stay scoped to the assigned task" over "Don't work on unrelated code"
- **No filler** — no "comprehensive", "robust", "seamless", "leverage"

### 2d — Create supporting files if needed

Agents are self-contained in a single flat `<agent-name>.md` file — the stub and codex-agent-toml wiring both hard-require that shape. Only add supporting files when:
- **`references/`**: The agent needs a complex checklist, schema reference, or detailed error-handling guide that would exceed the AGENT.md length
- **`scripts/`**: The agent runs deterministic validation that should not be left to LLM interpretation

Reference all supporting files from AGENT.md with `{baseDir}/references/filename.md` paths.

### 2e — Write the files

Create the directory structure and write all files. Use `Write` for new files.

## Phase 3 — Self-review

Before showing the agent to the user, read the quality checklist and verify the generated agent against it.

```
Read {baseDir}/references/quality-checklist.md
```

Walk through each item. Fix any failures silently — do not present an agent that fails its own checklist.

## Phase 4 — Library review

Invoke the `bilbo:reference` skill to find the library sources on agent architecture best practices, and critique the generated agent against its answer.

### 4a — Submit for review

Invoke `bilbo:reference` with a query naming the topic (agent architecture best practices). Read its cited answer, then review the full generated AGENT.md against it with this review question:

> "Review this agent definition for quality, best practices compliance, and potential issues. Check: single-responsibility adherence (does it try to do too many things?), tool selection (too many tools? missing tools? ungated high-risk tools?), error handling (does it define failure modes and exit strategies?), context engineering (does it minimize context overhead? are summaries condensed?), delegation protocol (if it receives from or sends to other agents, is the interface well-defined?), guardrails (does it have boundaries for retries, scope, and escalation?). Here is the agent definition: [full AGENT.md content]"

### 4b — Present results

Show the user:
1. The generated agent (full AGENT.md and any supporting files).
2. The library review findings.
3. Any changes you recommend based on the review.

Ask the user which library suggestions to incorporate.

### 4c — Apply feedback

Revise the agent based on user decisions and library feedback. Re-run the self-review checklist after changes.

### 4d — Library miss protocol

If `bilbo:reference` finds no library source on the topic, say so, note that the review was skipped and proceed on judgment - there is no external fallback to retry. The generated agent is still valid - only the library review step is blocked.

## Phase 5 — Finalize

After the user approves:

1. Confirm all files are written to disk.
2. Run `wc -l` on the AGENT.md to report final line count.
3. Wire it up: switch the host from the repo that provides the agent set (or tell the user to). Phase 2 wrote the agent into that repo's source tree; a NEW agent is not linked into `~/.claude` or `~/.codex` until a switch, because the farm is enumerated from the store copy.

## Output

Report concisely:
- Agent path and file list
- AGENT.md line count
- Architecture pattern used
- Library review summary (if performed)
- How the agent is spawned (by which orchestrator, or directly)

No congratulations, no filler, no summary of what you did.

## Hard prohibitions

- Never generate an agent without gathering requirements first (Phase 1). Jumping straight to generation produces unfocused agents with vague responsibilities.
- Never create a multi-responsibility agent. If the requirements describe more than one clear job, decompose into multiple agents and explain to the user why separation matters.
- Never write a `description` field without stating the agent's single responsibility and who spawns it.
- Never give an agent more tools than it needs. Each unnecessary tool increases selection ambiguity and token overhead.
- Never skip error handling design. Every agent must define what happens when it fails.
- Never skip the self-review checklist (Phase 3). Catching issues before the user sees them is the whole point.
- Never loop when `bilbo:reference` finds no library source for this topic - accept it and proceed, noting the gap.
- Never fabricate library review feedback. If the review was not performed, say so.
