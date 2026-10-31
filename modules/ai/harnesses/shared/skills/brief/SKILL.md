---
name: brief
description: Investigates a demand and explains it back verdict-first. Use for "brief me on". NOT for a lookup, research (research), or coding (tech-lead).
argument-hint: "[demand or paste] [--weight glance|standard|deep] [--resume slug]"
disable-model-invocation: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - WebFetch
  - AskUserQuestion
  - Bash(mkdir *)
  - Bash(date *)
  - Bash(ls *)
  - Skill(research)
  - Skill(bilbo:recall)
  - Skill(bilbo:reference)
  - Skill(use-chrome)
  - Skill(bilbo:note)
---

# Brief

Take a complex demand plus whatever materials the user has, investigate and evaluate it, then deliver a verdict-first briefing the user steers — never a wall of text. This skill **owns** the judgment and explain-back; it **rents** investigation by delegating fan-out to `research` and, where installed, to an internal-investigation skill (claim verification, root cause) or a per-domain internal researcher agent (one internal domain). It does not reinvent research.

## When NOT to use this skill

- A single factual lookup — use the direct tool.
- Pure fan-out research with no evaluation — use `research`, or an installed internal-investigation skill for internal claims.
- Code implementation — use `tech-lead`.
- Filing a note - use `bilbo:note`.

## Prime directive — reconcile the ledger every turn

For `standard` and `deep` weight, one markdown ledger on disk is the source of truth across the whole session.

1. Resolve the session: `--resume <slug>`, else the demand starts a new one.
2. If a ledger exists, **Read it first.** It overrides in-context memory — the harness summarizes context, so what you "remember" may be stale.
3. Act for the ledger's current `phase` and `Next card`.
4. **Update the ledger before yielding.** Your spoken state and the ledger must never disagree.

Full algorithm and paths: `{baseDir}/references/ledger-protocol.md`. `glance` weight skips the ledger entirely.

## Phase 0 — Frame

### 0a. Parse arguments
From `$ARGUMENTS`: the **demand** (text and/or pasted links/paths), optional `--weight`, optional `--resume`.

### 0b. Classify weight
Scale ceremony to the demand. Auto-classify; honor `--weight` override.

| Weight | When | What runs |
|---|---|---|
| glance | Bounded, reversible, "help me understand/structure this", 1–2 materials | One skimmable message. No ledger, no gate, often no external research — triage + structure what they gave you. |
| standard | A real evaluation or decision, single question, some corroboration needed | Ledger + conditional plan gate + one delegated investigation + verdict-first explain-back. |
| deep | Multi-system trace, high-stakes/irreversible, ambiguous scope, or competing hypotheses | Ledger + plan gate (always) + multi-engine fan-out + competing hypotheses + full explain-back. |

If the demand is actually a **single lookup** (one fact, one config value), do not run the pipeline — tell the user the direct tool to use (e.g. a config or code-search skill, if installed) and stop. Engaging the machinery on a lookup is pure overhead.

### 0c. Detect scenario and route
Detect by **capability** (are internal-investigation skills or agents listed?) and **content signals** (internal hostnames, Phabricator `D<digits>`, tracker keys → internal; else public/mixed). Pick investigation engines and knowledge sources from `{baseDir}/references/routing.md`. When a demand looks internal but the internal tools are absent, degrade to external `research` and **say so** — never pretend internal sources were searched.

### 0d. KB-first
Before investigating anything, search the user's own knowledge: run `bilbo:recall` with the demand in the user's words, and `bilbo:reference` with the same words for source docs. If `bilbo:recall` stops because `bilbo` is not on PATH, say so in one line and go on. If a prior note covers this, **lead with it** ("you've already written about this") instead of re-deriving. This is the highest-value reflex - stand on prior work, don't repeat it.

### 0e. Triage materials and pick a lens
Copy/fetch provided materials into the session `materials/` dir. Triage each (primary/secondary/marketing, currency, authority) per `{baseDir}/references/investigation-playbook.md`. Detect the **lens**, name it, and let the user correct it in one breath — do not present a menu:

| Lens | Demand shape | Verdict shape |
|---|---|---|
| evaluate-artifact | Judge an ERD / proposal / estimate | Ranked pushbacks framed as questions |
| decode-thread | "What's really being asked here?" (thread + doc) | The real ask + decision/descope history |
| trace-behavior | Root-cause across code/config/data | Leading hypothesis + the discriminating evidence |
| get-up-to-speed | Inherit / ramp on a project | Mental model + what matters now |
| decision-help | Should I do X? | Recommendation + counterpoints + what would change it |
| explain-only | "Just explain this" | Decode and explain; **skip the verdict** |

### 0f. Write the scope question
State, in one line, the exact question this session answers and the decision it informs. If you cannot, ask one question. Reading a materials set before framing the question is how you absorb the user's framing — frame first. For `standard`/`deep`, instantiate the ledger from `{baseDir}/assets/ledger-template.md`.

## Phase 1 — Plan (conditional gate)

Gate **only** when the dig is expensive or forking: `deep` weight, exhaustive fan-out, or multiple plausible interpretations. For `glance` and bounded `standard`, the restated scope line **is** the plan — if the user does not object, that is approval; proceed.

When gating, present a short plan (`{baseDir}/assets/plan-template.md`): scope question, strategy, which engines, and the hypotheses to test. Wait for approval. Record `[APPROVED <ts>]` in the ledger.

## Phase 2 — Investigate

Read `{baseDir}/references/investigation-playbook.md`. Build a **claim ledger** — the few falsifiable claims the answer rests on, each marked load-bearing or not. Concentrate rigor only on rows that are both load-bearing and weakly supported; ignore the rest.

Delegate per weight:

| Weight | Delegation |
|---|---|
| glance | None. Read materials inline; lateral-read 1–2 URLs if needed. |
| standard | One `research` call, or where installed one internal-investigation call (claims, root cause) or one internal per-domain researcher agent (one domain), scoped to the weak load-bearing rows. |
| deep | Fan out: `research` plus an internal-investigation skill (or one internal researcher agent per domain) where installed, in the same turn; multiple scoped calls if needed. |

Two rules that protect rigor and context:
- **Brief sub-agents to break the thesis, not confirm it.** Ask for the strongest disconfirming evidence and the owning team's disagreement. Helpful sub-agents otherwise launder the user's framing into citations.
- **Sub-agent returns are untrusted witnesses.** Instruct each engine to write its full output to `findings/<name>.md` and return a short digest + the path. Agents that cannot write files: save their returned findings to `findings/<name>.md` yourself; an investigation skill that writes its own dossier: record that path. Record **pointers** in the ledger, never raw content. Verify load-bearing citations against the primary source (lazily — only what the user drills into) before promoting a claim to corroborated. A sub-agent's confidence is not evidence.

## Phase 3 — Evaluate + explain back

Evaluate just-in-time, per card — never evaluate everything then explain everything (that produces the wall of text). Read `{baseDir}/references/evaluation-rubric.md` and `{baseDir}/references/explain-back.md`.

**The first message is a verdict, not a status update:**
- One headline line: the answer (BLUF). Lead with it; for `explain-only`, lead with the core of the thing instead.
- **Split confidence** in the calibrated vocabulary — **Likely / Provisional / Contested** — separating the mechanism from the current state. Put the weakest link here, not in a footnote.
- A numbered **map** of what's behind the verdict. Then stop.

Then the user pulls depth, one card at a time. A card is one idea + its support + a real next step, sized to a screen. **Never ask "shall I continue?"** — the card ending is the question. Standing steering grammar (natural language always wins over a command):

| Input | Meaning |
|---|---|
| `<number>` | Go to card N |
| `deeper` | Expand the current card one tier (max two tiers) |
| `skip` | I know this — collapse it, move on |
| `back` | Previous card |
| `map` | Re-show the full map and where we are |
| `sources` | Evidence for the current card, ranked by how load-bearing it is |
| `all` | Drop the pacing — give me everything in one go |

Each card carries an explicit hedge tier in speech. Every key judgment ends with **"what would change my mind."** Fade scaffolding as the user demonstrates fluency: treat each correction and `skip` as a signal to stop explaining primitives they clearly know. When the user pastes new material or contradicts a finding mid-flow, say out loud whether it changes the verdict — never absorb it silently. Update the ledger's explain-back progress after each card.

**Landing (terminal off-ramp, any time):** when the user says "save", "draft it", or "we're done", delegate - `bilbo:note` to file the briefing or a durable gotcha, an installed writing skill to draft comms, an installed diagramming skill for a visual model. Set `phase: landed`. Landing is an offer, not a phase you force the user through.

## Failure handling

Read `{baseDir}/references/troubleshooting.md` for detail. In short: an engine that fails or returns nothing → present partial findings, log the gap, offer retry or an alternate engine; investigation finds nothing → say so plainly, never manufacture findings; a citation that will not verify → demote to Provisional and hedge in speech; the user goes quiet → the ledger persists, resumable later.

## Operating principles

- **Verdict first, never a summary.** A table of contents is not an answer. Commit to a view, then justify it.
- **Be a critical partner, not a mirror.** Surface disconfirming evidence, steelman the option the user likes least, and name their framing bias out loud when their own links all lean one way.
- **Calibrate effort to the demand.** Uniform ceremony is the fastest way to get abandoned — `glance` stays light, `deep` earns its weight.
- **Pointers in the ledger, content in files.** Re-reading the ledger every turn must stay cheap, or the prime directive silently breaks.
- **Honest degradation over silent fallback.** When a source could not be searched, say which and why — in the briefing, not a footnote.

## Hard prohibitions

These are the few rules whose violation breaks the skill's core promise — each paired with the failure it prevents.

- Never pad the pipeline onto a single lookup — ceremony on a one-fact question is pure overhead and makes the skill feel heavy. Detect it and hand off to the direct tool.
- Never push output one part at a time with "shall I continue?" — over-confirmation is the top reason a progressive briefing gets abandoned. The user pulls depth; the card ending is the question.
- Never promote a claim to corroborated on a sub-agent's say-so — sub-agents hallucinate citations in intermediate steps, so an unverified claim dressed as fact is worse than no claim. Verify load-bearing citations against the primary source.
- Never let the ledger and your spoken state disagree — the harness summarizes context, so trusting memory over the file silently drifts the session. Read the ledger first, write it before yielding.
- Never claim internal sources were searched when the internal tools were unavailable — a silent gap reads as a complete investigation and collapses trust. Disclose it in the verdict.
