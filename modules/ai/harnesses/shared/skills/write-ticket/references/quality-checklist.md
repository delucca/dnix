# Quality checklist, severity/priority, and anti-patterns

## The "is this a good ticket?" checklist

Use this to self-check a drafted ticket, or to score one in audit mode. In audit mode, report failures as findings, most-severe first.

- [ ] **Title** is specific and searchable — not "fix bug" / "feature request".
- [ ] States the **why** (problem / value), not only the what.
- [ ] Describes the **problem/outcome**, does not dictate the **implementation**.
- [ ] Has **binary, testable acceptance criteria** — a few sharp ones, not a 15-item wall.
- [ ] **Right-sized** — roughly one PR / a few days. If not, split *vertically* (see SPIDR in frameworks-and-evidence.md).
- [ ] **Non-goals / scope boundaries** stated.
- [ ] **Detail matches the reader** — thin if they can ask you, thick if async, fully encoded if an AI agent.
- [ ] **Linked** to designs / docs / related work; not a duplicate.
- [ ] Exactly **one issue** per ticket.
- [ ] (Bug) has **repro steps + environment + expected/actual + evidence**, and **severity & priority set separately**.
- [ ] (Non-user-facing work) is a Task/Spike/chore, not a fake `As a user…` story.
- [ ] Language is plain — no untestable adjectives ("intuitive", "seamless", "robust").

## Severity vs priority (bugs) — never conflate

They are independent axes. Make both explicit.

- **Severity** = technical/functional impact on the system. Objective; a QA/engineering call.
- **Priority** = urgency to fix. Business-driven; a product call.

Illustrations of why they diverge:
- **High severity, low priority**: a crash only triggerable by entering 50 phone numbers — catastrophic but nobody hits it.
- **Low severity, high priority**: the logo is misaligned and the investor demo is tomorrow.

If a tracker offers only one field, still reason about both and put the other in the description. If everything is marked "Critical", the field has lost its signal — push back.

## Anti-pattern catalog (what to flag)

**Ticket-level**
- Vague, non-searchable title.
- **Solution-in-the-ticket** instead of the problem ("I want a dropdown with autocomplete" vs "I want to find products fast") — forecloses better solutions.
- **Fake story** — technical work wrapped in `As a user…` for no reason.
- No acceptance criteria — *or* **acceptance-criteria theater** (a long list that looks rigorous but really signals an oversized, unsplit ticket).
- (Bug) missing environment / repro / expected-vs-actual.
- Multiple unrelated issues in one ticket.
- "No more than a title" — an unactionable stub.

**Backlog / epic-level**
- **Catch-all epic** ("Q3 Bugs", "Tech Debt") — never completes, no measurable progress.
- **Title-only epic** — every stakeholder reads a different expectation into the vague name.
- Horizontal / component slicing instead of vertical.
- Orphaned / zombie tickets — created, never touched, now factually wrong as assumptions shifted.
- Backlog as an idea dumping-ground; stale items never pruned (distorts age/velocity/count metrics).

**Process-level**
- One person specs both the *what* and the *how* (kills negotiability).
- Tickets used as a control mechanism rather than a shared statement of intent.

## What the evidence actually supports

Stay honest about which "best practices" are proven vs. folklore:

- **Strongly evidenced** — a structured **required-field template/form measurably helps** (largest study: ~1.9M GitHub issues; templated median resolution 103 days vs 381 untemplated; YAML forms beat free-text). If you change one structural thing, adopt a template.
- **Strongly evidenced** — developers value **reproduction steps** above all; missing them → non-reproducible + delayed fixes.
- **Folklore, largely unvalidated** — INVEST as a *causal* driver of outcomes. Good heuristic, not proven law; don't wield it as a hard gate.
- **Folklore, partly refuted** — "duplicate bug reports are pure waste": merged duplicates add real diagnostic value.
- **Confound to stay humble about** — "better ticket → faster fix" is muddied by inherent difficulty and by organizational/social distance. A good ticket helps; it isn't the only lever.
