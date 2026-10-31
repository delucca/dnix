# Agent Quality Checklist

Distilled from "Building Agents Best Practices" research. Use this to evaluate a generated agent before presenting it.

## Frontmatter

- [ ] `name` is kebab-case, no spaces, no capitals, max 64 chars
- [ ] `name` matches the directory name
- [ ] `description` states the agent's single responsibility
- [ ] `description` states who spawns the agent (orchestrator, skill, or user)
- [ ] `description` includes when to use it (trigger conditions or proactive usage)
- [ ] `description` is under 1024 characters
- [ ] `description` includes negative triggers if scope could be ambiguous
- [ ] `tools` lists only what the agent actually needs (minimal viable set)
- [ ] Bash permissions use glob patterns (`Bash(git *)`, not `Bash(*)`)
- [ ] `model` matches task complexity (haiku for simple, sonnet for moderate, opus for complex)
- [ ] `effort` matches reasoning depth needed
- [ ] `isolation: worktree` is set if the agent modifies files

## Single Responsibility

- [ ] The agent has one clear job, stated in a single sentence
- [ ] No mixed concerns (e.g., implement AND review, generate AND deploy)
- [ ] If the agent orchestrates, it does NOT write code directly
- [ ] If the agent implements, it does NOT make architectural decisions beyond its scope

## Tool Design

- [ ] No tool overload — each tool serves a distinct purpose the agent needs
- [ ] High-risk tools (delete, deploy, push, send) have documented gating or approval steps
- [ ] MCP tools are scoped with glob patterns where possible
- [ ] The agent does not have both `Agent` (spawn) and heavy implementation tools — pick orchestrator or worker

## Workflow

- [ ] Workflow has numbered steps with clear actions
- [ ] Each step uses imperative language ("Read the file", not "You should read")
- [ ] Gate conditions are explicit where the agent must verify before proceeding
- [ ] Input format is documented (what the agent expects to receive)
- [ ] Output format is documented with a concrete example structure
- [ ] Output is condensed — summaries over raw dumps to preserve orchestrator context

## Error Handling

- [ ] Failure modes are defined (what happens when the agent cannot complete its task)
- [ ] Exit strategies exist (structured "cannot complete" response with reasons)
- [ ] Retry boundaries are set (maximum attempts before escalation)
- [ ] Escalation path is clear (who to escalate to: orchestrator, user, or another agent)
- [ ] Validation step exists before returning (lint, tests, or structural checks)

## Context Engineering

- [ ] The agent reads existing code/patterns before acting (not just the delegation prompt)
- [ ] Summaries returned to orchestrators are condensed (not raw logs or full file contents)
- [ ] Delegation prompts to subagents are documented as self-contained (subagents have fresh contexts)
- [ ] No duplicate information that could be derived from reading the codebase
- [ ] Every instruction passes the test: "Would removing this cause the agent to make mistakes?"

## Key Behaviors

- [ ] 3-5 bullet points covering scope discipline, pattern adherence, error handling, and summary format
- [ ] Scope discipline is explicit ("Stay scoped", "Do not expand beyond the assigned task")
- [ ] Decision-making stance is clear (decide-and-document vs. block-and-ask)
- [ ] Explains *why* behind constraints, not just *what* — reasoning over rigid MUSTs

## Writing Quality

- [ ] No filler words: "comprehensive", "robust", "seamless", "leverage"
- [ ] No second-person narration ("You should...", "You will...")
- [ ] Consistent terminology throughout (one term per concept)
- [ ] Positive phrasing where possible
