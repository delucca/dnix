# Skill Spec: tldr

> Status: Draft | Date: 2026-07-31

## Target User
The user, invoking their own AI agents (Claude Code, Codex) day to day. They just received a
long, over-structured agent response and wants the substance in seconds, not a re-read.

## Trigger Scenario
The agent answered with a wall of text: headers, nested bullets, process narration.
The user types `/tldr` (or "tldr that", "shorter", "too long") to get a short,
human-readable digest of what was just said, and to keep the agent terse afterward.

## Trigger Phrases
**Should trigger:** "condense that", "tldr", "shorter", "too long, summarize",
"be less verbose", "just give me the idea", "make that readable", "/tldr"
**Should NOT trigger:**
- Rewriting text to sound human / de-AI
- Teaching or walking through a topic interactively → `explain`
- Investigating and evaluating a demand verdict-first → `brief`
**Proactive conditions:** None — user-invoked only.

## Success Criteria
1. The digest opens with a single-sentence outcome (the answer / what happened), not context.
2. Digest fits the budget: ≤120 words / ≤10 lines at default weight.
3. Every figure, path, command, and identifier that survives is verbatim from the source.
4. Any question to the user, blocking decision, or required action from the source
   survives into the digest — never condensed away.
5. No new claims: the digest contains nothing that is not in the source response.
6. Subsequent replies in the session stay terse until the user asks for depth.

## Expected Output
A short digest in chat: one headline sentence, then at most 5 plain-prose bullets,
then (only if present in the source) an "On you:" line with the pending question or
action. No headers, no tables, no nested bullets.

## Configuration Parameters
| Parameter | Default | What it controls |
|-----------|---------|-----------------|
| target (argument) | last substantial agent response | what to condense: inline text, a file path, or empty |
| --budget N | 120 | word ceiling for the digest |
| --once | off | condense only; do not switch the session to brief mode |

## Follow-up Actions
- Ask "expand <bullet>" to get the dropped detail behind any line.
- Ask for the original: it is still in the transcript, nothing is destroyed.
- An installed humanizing skill, if one is listed, if the digest will be pasted somewhere human-facing.

## Dependencies
| System | Required/Optional | Purpose |
|--------|------------------|---------|
| None (conversation transcript) | Required | source text lives in-session |
| Read | Optional | when the target is a file path |
**Code-mode wrapper needed:** No — no MCP usage.
**Local env requirements:** None.

## Targets
| Harness | Model(s) | Per-target notes |
|---------|----------|------------------|
| claude-code | fable/opus/sonnet | primary |
| codex | default | served via ~/.codex/skills symlink stub; no harness-specific calls |

## Cost Estimate
| Metric | Estimate |
|--------|---------|
| Tool calls per run | 0–1 (Read only when target is a file) |
| Main cost driver | none — pure rewrite |
| Parallelism opportunities | None |
| Worst-case (all fallbacks tried) | 1 call |

## Failure Modes
| Failure | Recovery |
|---------|---------|
| No prior substantial response and no argument | Ask: "What should I condense?" — do not invent a target |
| Source is already short (≤ budget) | Say so in one line; tighten wording only if it helps |
| Source contains a user-facing question | It MUST appear in the digest's "On you:" line |
| Budget makes the digest lossy on a critical constraint | Keep the constraint, drop a lower-value bullet instead |

## Fallback Chains
Source: [text to condense]
1. `$ARGUMENTS` inline text
2. `$ARGUMENTS` as an existing file path (Read)
3. Most recent substantial agent response in this conversation
4. Terminal — ask the user what to condense.

## Build Decisions
**Environment detection needed:** No
**Python scripts + unit tests required:** No

## Out of Scope (v1)
- Auto-condensing every response via hooks — behavior change belongs to settings/hooks, not a skill.
- Summarizing external documents at length - that is `research`/`bilbo:ingest` territory.
- Voice/tone rewriting.

## Design Decisions
### Decision: rewrite-only, no re-answering
**Chose:** treat the source response as the only ground truth
**Over:** re-running the task "but shorter"
**Because:** re-answering can silently change facts; condensing must be lossless on substance, lossy on padding.

### Decision: session brief-mode as a side effect
**Chose:** after one invocation, subsequent replies stay terse (opt out with --once)
**Over:** condense-only semantics
**Because:** the user's stated need is "make the agent be less verbose", not just "summarize once".

## Known Gotchas
- The most common failure of summaries is dropping the ask (a question or pending
  decision buried in the wall of text). Criterion 4 exists for this.
- Skill descriptions in this dotfiles setup must stay short to fit Codex's skill-block
  budget (see dotfiles commit 72b4e00).
