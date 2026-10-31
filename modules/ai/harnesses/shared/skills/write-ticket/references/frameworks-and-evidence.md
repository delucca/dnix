# Frameworks, evidence, and rationale

Load this when the user asks *why*, or when a decision needs the deeper reasoning. It backs the two rules and the workflow in SKILL.md.

## The mental model

A ticket is a durable, self-contained unit of *intent* that lets someone who isn't you — a teammate in another timezone, future-you, or an AI agent — act correctly without a synchronous conversation. The two questions it must answer instantly: **why does this matter** and **how will we know it's done**.

## INVEST (Bill Wake, 2003) — story quality heuristic

**I**ndependent, **N**egotiable, **V**aluable, **E**stimable, **S**mall, **T**estable.

- Use it as *emergent refinement guidance*, not a blocking gate (the common misuse).
- Honesty flag: Wake himself would now drop **Estimable** ("the most-abused aspect"), and there is essentially no large-sample empirical validation that INVEST *causes* better outcomes. Excellent thinking tool; not law.

## The 3 Cs (Ron Jeffries, 2001)

**Card** (a minimal token) / **Conversation** (where the real detail lives) / **Confirmation** (acceptance tests). The load-bearing idea: the card is not the story — the conversation is. This is the root of "keep tickets thin." It is exactly what async work and AI agents partially overturn (see the detail rule): when there is no reliable conversation, the conversation must be pre-written.

## Acceptance criteria — two legitimate styles

1. **Given-When-Then / Gherkin (BDD)** — Dan North & Chris Matts (~2006). `Given <context>, When <event>, Then <outcome>`. Now the dominant format. Keep to **3–5 steps**. Best for complex business rules, multiple paths, or criteria that will be automated as executable specs.
2. **Rule / checklist style** — plain testable bullets. Best for features with many independent, non-linear requirements, or when scannability beats executable precision.

Either way: binary (pass/fail), unambiguous (one interpretation), behavior not implementation. Best produced collaboratively (a "Three Amigos" pass: product + dev + test) and written *before* estimation. Acceptance criteria (specific to this item) are not the Definition of Done (a quality bar on every item).

## DoR vs DoD

- **Definition of Done** — firm, uncontested; every item must meet it (code reviewed, tests passing, docs updated, deployable…).
- **Definition of Ready** — optional and contested; not part of Scrum. Useful as lightweight refinement discussion points; harmful as a rigid gate (creates gatekeeping and delay). Don't over-institutionalize it.

## DEEP — health of the backlog (the set, not one ticket)

**D**etailed-appropriately (near-term refined, far-term coarse), **E**stimated (precision decreases with depth), **E**mergent (it *should* change; a static backlog is a red flag), **P**rioritized (strict value order).

## Sizing and splitting

Small wins for a real reason: batch-size economics (halving batch size roughly halves queue and cycle time) — faster feedback, cheaper to cancel/reprioritize, bottlenecks surface, morale from frequent wins.

Sizing heuristics are directional; calibrate to your team's cycle time. Signs too big: >~5 acceptance criteria, can't be confidently estimated, bundles multiple paths/data types/rules, or a title abstract enough that anyone can read any expectation into it.

**Split vertically, never by layer.** A slice that spans UI+logic+data and delivers end-to-end value beats separate "UI ticket / DB ticket". **SPIDR** (Mike Cohn):
- **S**pike — carve off a timeboxed investigation when there's a genuine unknown.
- **P**ath — split by alternate user journeys (card vs Apple Pay).
- **I**nterface — ship a basic UI first, richen later.
- **D**ata — narrow the data scope first (1 format → many later).
- **R**ules — relax a business rule initially, tighten later.

On a brand-new system, start with a **walking skeleton**: a tiny end-to-end slice exercising the whole build/deploy/test path before any real feature.

## EARS (Mavin et al., 2009) — for airtight requirements

Templates that kill ambiguity: ubiquitous (`The <system> shall <response>`), event-driven (`When <trigger>, the <system> shall <response>`), state-driven (`While <state>, …`), unwanted-behavior (`If <condition>, then the <system> shall <response>`), optional (`Where <feature>, …`). Worth reaching for when acceptance criteria must be unambiguous (safety/compliance/high-stakes).

## Tool philosophies — the durable, portable laws

The trackers disagree loudly; the agreements are the laws worth keeping:
1. Titles are the interface — make them specific.
2. Small beats big — every tool caps size aggressively.
3. Structure comes from templates/forms, not prose discipline.
4. Separate the what/why from the how.
5. Explicit boundaries / non-goals prevent scope creep (Shape Up's "no-gos" and "rabbit holes" are the sharpest version).
6. A recurring intake ritual is non-negotiable — refinement (Jira), triage (Linear), or the betting table (Shape Up).

Genuine forks to choose deliberately: user-story format (Jira uses it; Linear says write plain issues) · big groomed backlog (Jira) vs no backlog (Shape Up) · estimate everything (INVEST) vs fixed appetite/variable scope (Shape Up) · PO-authored vs the-doer-writes-it (Linear).

## AI-era ticket writing (specs as agent input)

When the consumer is an autonomous coding agent, the ticket becomes context for its window, and the "conversation" it can't have must be written down.
- **Spec-driven flow**: Specify → Plan → Tasks → Implement, gated, small reviewable units; the spec is the source of truth the agent validates against.
- An agent spec needs more than a human ticket: exact commands, testing framework/location, explicit paths, *real code examples of house style*, and a boundary system — ✅ Always / ⚠️ Ask first / 🚫 Never.
- But not infinite detail: model instruction-adherence drops as instruction count climbs ("curse of instructions"). Prefer modular, cross-referenced specs; feed one task at a time.
- Keep a human in the loop: LLMs sound *more* confident when hallucinating, so AI-drafted acceptance criteria can look authoritative and be wrong. Best pattern — give AI a rough brief, let it expand into structured story + criteria, then edit. Never let it skip the *why*.
