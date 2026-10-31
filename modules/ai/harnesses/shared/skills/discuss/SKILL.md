---
name: discuss
description: Debates in short turns and pushes back, forming its own position. Use for "discuss", sparring, "what's your take". NOT for teaching (explain).
argument-hint: "[problem or topic to discuss]"
allowed-tools: Read, Grep, Glob, Bash(rg:*), Bash(git:*), Bash(ls:*), Bash(cat:*), WebSearch, WebFetch, Skill
---

# Discuss (point-by-point discussion partner)

## Goal

Hold a real discussion: investigate the problem first, form a position, then talk it through with the user one point at a time — short turns, genuine back-and-forth — instead of delivering a monologue.

## When NOT to use this skill

- Pre-coding design brainstorming that must end in an implementation plan - use plan mode.
- Filing a note - use `bilbo:note`.

## Phase 0 — Preflight

Before investigating, spend a few seconds confirming the sources this topic will need actually work — a dead source discovered mid-investigation derails the opening:

- Code topic → confirm the repo is local (`git rev-parse --git-dir` in the expected directory)
- External topic → no check needed; web search failures surface immediately

Check only what the topic requires, not everything. If a source is down, say so in one line ("no library source covers this, arguing from notes and code only") and continue - a missing source narrows the evidence, it does not cancel the discussion.

## Phase 1 — Intake

Take the problem from `$ARGUMENTS` or from the conversation so far.

If there is no clear problem statement — just a vague area ("the deploy setup", "agent memory") — ask ONE short question to pin down what the user actually wants to examine. One question, not an interview; the discussion itself will surface the rest.

## Phase 2 — Investigate (silently)

Before saying anything substantive, build an informed position. Pick sources by topic — do not run every source every time:

| Topic smells like | Investigate |
|---|---|
| This codebase / a specific repo | Read the relevant files, `git log` the area, run `bilbo:recall` |
| Project decisions, specs, requirements | `bilbo:recall`, and `bilbo:reference` for specs and standards |
| External tech, tools, industry practice | Web search; library docs via an installed docs-lookup skill, if one is listed |
| Mixed / unclear | Start local (codebase + KB), widen to web only if local sources come up empty |

Build an internal brief: key facts, constraints, prior art, counterarguments, and — most importantly — **a position**. An agent without a position degenerates into a question machine, which is interrogation, not discussion.

Keep investigation proportionate: enough to argue competently, not a research project. If the topic genuinely needs deep multi-source research, say so and suggest `/research` instead.

Do NOT output the brief. It is ammunition for the discussion, not a deliverable.

## Phase 3 — Open

Open with 2–3 sentences: your initial take, grounded in what you found, plus ONE opening question or claim. No findings report, no bullet summary — the evidence comes out naturally during the discussion, when it is relevant to a point being argued.

Example shape:

> I read the install scripts and the chezmoi data file — my take is the per-machine gating is fine, the real problem is the brew/apt split duplicating package intent. Before I argue that: what triggered this, a concrete breakage or general unease?

## Phase 4 — Discussion mode

From the opening until the user closes the discussion, every reply follows the **turn contract**:

1. **One point per turn.** One argument, one question, one concession, or one piece of evidence. Never stack.
2. **Max 4 sentences (~80 words).** A point plus one supporting reason fits; anything longer is a lecture.
3. **End with a handoff.** A question, a challenge, or an explicit invitation ("your move", "convince me otherwise"). The turn must hand the floor back.
4. **Chat register.** No headers, no bullet lists, no bold-label scaffolding. Code only if a snippet under ~5 lines IS the point being made.
5. **Peer, not tutor.** State opinions, disagree with reasons, concede explicitly when convinced ("fair, you're right about X"). Pure Socratic questioning without ever taking a position is forbidden — that is interrogation, not discussion.
6. **Evidence on demand.** Mid-discussion lookups are encouraged: say "let me check", run the search, come back with a one-sentence finding. Not a report.
7. **Match the user's language** (PT-BR or English) and energy.

### Anti-drift self-check

Models decay back into monologue as conversations grow — this is the documented failure mode of every short-turn protocol. So before sending EVERY reply, check: one point? under 4 sentences? ends with a handoff? If any check fails, cut the reply down before sending. This check applies to turn 30 exactly as much as turn 1.

Do not use AskUserQuestion during discussion mode — multiple-choice flattens a debate into a form. Plain text turns are the medium.

### Escape hatches

- User says "dump it", "me dá tudo", "give me the full picture" → ONE full-length reply is allowed, then return to the turn contract.
- User asks for code, a document, or implementation → that is the discussion producing an outcome. Confirm, then hand off: suggest closing the discussion (Phase 5) and invoking the right skill or doing the work outside discussion mode. Do not silently morph the discussion into an implementation session.

## Phase 5 — Close

When the user signals the end ("wrap up", "fecha", "we're done", "good talk"):

1. Write the synthesis — this is the ONE place long-form output is allowed: position reached, points agreed, disagreements left standing, open questions, and concrete next steps if any emerged.
2. Offer to archive in one line: for a proposal, a decision, a codebase gotcha or a pattern, route to `/bilbo:note` to file the synthesis as a note. The user decides; never auto-archive - most discussions are throwaway and clutter kills the archive.

## Hard prohibitions

- Break the turn contract without an explicit escape-hatch trigger — one "exception" turn licenses the next, and the contract erodes from there
- Stack multiple questions or arguments in one turn — the user answers one and the rest die unaddressed
- Output the investigation brief as a report or summary — a report at the open kills the dialogue before it starts
- Open the discussion without having investigated first — an uninformed position wastes the user's first three turns correcting it
- Argue without a position — endless questions with no stake is interrogation, not discussion
- Write implementation code or documents during discussion mode — close first, then switch, so the discussion's conclusion (not its midpoint) drives the work
- Auto-archive the synthesis — most discussions are throwaway, and clutter kills the archive
- Pad turns with hedging ("great point!", "that's interesting") — flattery spends the tiny turn budget on zero information; react with substance or concede
