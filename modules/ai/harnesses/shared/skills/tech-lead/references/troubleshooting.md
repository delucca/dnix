# Troubleshooting & Escalation Guide

## Error cases

| Situation | Action |
|-----------|--------|
| No plan provided | Ask the user for a plan before proceeding |
| Plan is ambiguous or underspecified | Ask clarifying questions before decomposing |
| User rejects task decomposition | Revise based on feedback and re-present |
| Developer fails to complete | Retry with more specific instructions (max 2 retries total per task), then escalate to user |
| Reviewer finds issues | Re-spawn developer with the reviewer's findings (counts toward the 2-retry limit) |
| Same task fails review twice | Stop. Report all findings and reviewer feedback to the user. |
| Worktree creation fails | Report error. Check if the branch already exists or the repo state is bad (detached HEAD, dirty index). |
| Integration conflict between tasks | Stop. Report the conflicting changes. Ask the user how to resolve. |
| Developer returns vague summary | Read key files in the worktree directly to assess before proceeding to review |
| Reviewer reports clean worktree | The developer likely failed silently. Re-spawn the developer with more explicit instructions. |
| Git push fails (branch protection, conflicts) | Report the error and the branch name. Ask the user to resolve. |

## Retry counting

Track retries per task, not globally. Each task gets a maximum of 2 implementation attempts (initial + 1 retry, or initial + reviewer-driven fix). The retry counter increments on:
- Developer failing to complete
- Reviewer finding issues that require re-implementation

It does not reset between these scenarios -- a task that failed implementation once and then failed review once has used both retries.

## When to escalate vs. retry

**Retry when:**
- The developer missed a specific requirement from the task spec
- The reviewer found a fixable issue (missing test, style violation, minor logic error)
- The error message is clear and actionable

**Escalate when:**
- The developer's approach is fundamentally wrong (solving the wrong problem)
- The reviewer raises architectural concerns that may affect the plan
- The same issue recurs after a retry (indicates a misunderstanding, not a mistake)
- Multiple tasks conflict with each other (requires plan-level thinking)
