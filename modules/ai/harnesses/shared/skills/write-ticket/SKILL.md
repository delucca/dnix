---
name: write-ticket
description: Creates or audits a tool-agnostic ticket (story, bug, spike, epic) with a clear why and testable criteria. Use for write a ticket. NOT for filing in a tracker (use-jira).
argument-hint: "[brief to write, or ticket to improve]"
allowed-tools: Read, Write, AskUserQuestion
---

Turn a rough brief into a well-formed, tracker-agnostic ticket — or take an existing ticket and rewrite it to that standard.

## When NOT to use this skill

- Actually filing or posting a ticket in a tracker — use the tracker's own skill (e.g. `use-jira`).
- Authoring an ERD or design doc.

## Two rules that decide everything

Before anything else, hold these two rules. Every step below serves them.

1. **A ticket exists to answer two questions instantly: "Why does this matter?" and "How will we know it's done?"** Almost every weak ticket fails one of these. State the *why* (the problem or user pain), not just the *what*. Give *testable* done-conditions.
2. **Detail is a function of whether the reader can ask you.** Under-specify decisions that are still open (leave room to find a better solution); over-specify context that would otherwise need a live conversation. Scale to the consumer:
   - Co-located teammate who'll discuss it tomorrow → thin ticket is correct.
   - Async / remote / cross-timezone → write the context down; a missing detail costs a day.
   - **An AI coding agent → fully encode it.** There is no conversation to fall back on.

Never dictate the *implementation* in a ticket, no matter how detailed — describe the problem, outcome, and constraints, and leave the "how" to whoever builds it.

## Decide the mode

The input is `$ARGUMENTS` when invoked as a command, otherwise the current request and conversation.

- **Create mode** — the input is a brief, an idea, a bug someone hit, or "write a ticket for X". Go to *Create workflow*.
- **Audit mode** — the input is an existing ticket (pasted text or a file path) plus intent like "is this good?", "improve/review/rewrite this". Go to *Audit workflow*.

If a file path is given, `Read` it. Otherwise work from the pasted text or the conversation.

## Create workflow

1. **Pick the ticket type first — do not force everything into user-story format.**
   - **Story** — user-facing value. `As a <role>, I want <goal> so that <benefit>`.
   - **Task / chore** — technical work no user sees. Use FDD form `<action> the <result> for a <object>` (e.g. "Cache the token lookup for the auth middleware"), not a fake `As a developer…` story.
   - **Bug** — a defect. Centered on *reproduction*, not value.
   - **Spike** — a timeboxed *question to answer*; output is a decision, not shippable code.
   - **Epic** — a large outcome refined into stories later. Keep it thin (goal + success metric + scope), not a dumping ground.
2. **Gather the essentials.** Identify the *why*, the desired *outcome*, constraints, and non-goals. Note who/what will consume the ticket (rule 2).
3. **Do not invent facts.** If a load-bearing detail is missing — for a bug: repro steps, environment, expected vs actual; for a story: the actual user benefit — ask at most one or two targeted questions, or leave a clearly marked `<needs input: …>` placeholder. Never fabricate a version number, error string, metric, or acceptance condition.
4. **Load the matching template** from `{baseDir}/references/ticket-templates.md` and fill it.
5. **Write acceptance criteria** that are binary, unambiguous, and about behavior not implementation. Use Given/When/Then for rule-heavy or automatable flows, a testable checklist otherwise. See `{baseDir}/references/frameworks-and-evidence.md` if you need the deeper "how".
6. **Right-size it.** If it bundles multiple user paths, data types, or rules, or would take more than a few days, propose a **vertical** split (SPIDR: Spike / Path / Interface / Data / Rules — details in `{baseDir}/references/frameworks-and-evidence.md`). Never split by technical layer.
7. **Self-check** against `{baseDir}/references/quality-checklist.md`. Fix failures before showing the user.
8. **Output** the ticket in a single copy-paste block (see *Output format*).

## Audit workflow

1. **Read the ticket** and identify its type.
2. **Score it** against `{baseDir}/references/quality-checklist.md`. Produce findings, most-severe first. Common ones: missing *why*; no or untestable acceptance criteria; solution baked into the ticket instead of the problem; oversized/unsplit; (bugs) missing repro/environment or expected-vs-actual; severity and priority conflated or missing; vague non-searchable title; multiple issues in one ticket.
3. **Rewrite it** to fix the findings, staying faithful to the original intent. Preserve the author's facts; fill genuine gaps with `<needs input: …>` placeholders rather than guesses.
4. **Present** the findings list first (short, concrete), then the rewritten ticket in a copy-paste block.

## Output format

- Emit the ticket inside one fenced code block so it copies cleanly.
- Lead with a specific, searchable **title** (verb-led where natural; front-load the symptom/outcome + component). Never "fix bug" or "feature request".
- Keep the ticket **tracker-agnostic** by default. If the user named a tracker (Jira, Linear, GitHub, Phabricator), map fields to its conventions and note the mapping in one line beneath the block.
- Write in plain language. Avoid vague adjectives like "intuitive", "seamless", "robust" — they aren't testable.

## Edge cases

- **Brief too vague to type it correctly** — ask one clarifying question (what problem, or who's affected), then proceed. Don't stall on a full interview.
- **User wants it actually filed** in Jira/Linear/GitHub/Phabricator — produce the ticket text, then point them at the tracker's own skill (e.g. use-jira) to file it. This skill does not post.
- **Input is a huge epic or a whole feature** — don't emit one giant ticket. Write the epic thin, then propose the child stories as a short list (split vertically).
- **Existing ticket is already good** in audit mode — say so plainly and suggest only the highest-value tweaks, rather than manufacturing findings.

## References

Load only what the current step needs — these stay out of context until then.

- `{baseDir}/references/ticket-templates.md` — copy-paste templates for story, bug, spike, epic, and a Shape Up-style pitch.
- `{baseDir}/references/quality-checklist.md` — the audit checklist, severity-vs-priority, and the anti-pattern catalog.
- `{baseDir}/references/frameworks-and-evidence.md` — INVEST, the 3 Cs, acceptance-criteria styles, DoR/DoD, DEEP, SPIDR/splitting, EARS, evidence-vs-folklore, tool philosophies, and AI-era spec guidance. Load when the user asks *why*, or when a decision needs the deeper rationale.

## Hard prohibitions

- Never fabricate facts (versions, error text, metrics, repro steps, acceptance conditions), because every detail must trace back to the brief or it will mislead whoever builds the work. Ask, or mark `<needs input: …>`.
- Never dictate implementation — a ticket states the problem, outcome, and constraints, not the code, so the builder can find the best solution.
- Never force non-user-facing work into `As a user…` format, because a fake story hides the real work and adds no value; use a Task or Spike instead.
- Never conflate severity (technical impact) with priority (urgency) on a bug — they are independent fields, and collapsing them destroys triage signal.
- Never actually create, post, or edit a ticket in a real tracker. This skill produces text; filing is the tracker skill's job (e.g. use-jira).
