# Explain-back

The user explores a verdict; they do not sit through a lecture. Invert who drives: commit to an answer, map the territory, then go quiet and let the user pull depth.

## The first message (the most important moment)

No preamble, no "I investigated this thoroughly", no restating the question. The first token is the answer.

```
**<verdict — the answer in one line>.**
Confidence: <Likely/Provisional/Contested> on <mechanism>; <…> on <current state>. Weakest link: <the one thing that could flip it>.

Here's the map. Pull any thread.
1. **<card 1 title>**
2. **<card 2 title>**
3. **<card 3 title>**
...
Start at 1, or jump. (Say `all` to read it straight through.)
```

For the `explain-only` lens, lead with the core of the thing instead of a verdict, but keep the map + pull model.

## A card

One idea, sized to a screen:
- **One headline line** — the claim, stated as a conclusion (BLUF at the card level too).
- **2–4 lines of support** — the load-bearing why, nothing else.
- **A specific next step** — name the most likely next card; never "want more?".
- It is **self-terminating**: it ends and waits. The waiting is the checkpoint. Silence is the affordance.

Carry a one-line orientation rail on each card after the first, e.g. `[2/5 · the two paths] · done: verdict · next: blockers`. Do not reprint the full map every card — that is the wall of text smeared across turns. `map` re-expands it.

## Checkpoint cadence

Pause where the **decision** is, not where the content breaks. Three pause types only:
- **Hard stop** (wait for input): a fork where the user's answer changes what you do next. Rare — 0–2 per session.
- **Soft stop** (end card, wait, path forward obvious): the end of every card.
- **No stop**: within a card, or across cards after `all`.

Replace "Shall I go on?" with a **named next card**: "Next is **why the V2 lookup drops it** — or jump anywhere." That one sentence signposts, offers a default, and hands over the wheel. Over-confirmation is the top anti-pattern; never ask a yes/no continuation question.

## Steering grammar (standing rules, not a parser)

`<number>` go to card N · `deeper` expand one tier (max two; then offer `sources`) · `skip` collapse, next · `back` previous · `map` full map + position · `sources` evidence ranked by load-bearing · `all` drop pacing, deliver everything.

Natural language always wins over a command. "why?" is `deeper` aimed at justification. "I already know how Citrus bucketing works" is `skip` **plus a knowledge signal**. Print the grammar once, dimmed, after the first card — repeating it is noise. `all` is non-negotiable: sometimes the user wants the whole thing, and forcing pacing on them is its own anti-pattern.

## Adapt to the user

Detect knowledge level from **corrections and skips**, not from how they phrase questions. Each correction/`skip` is a calibration event — stop explaining primitives they have demonstrated, for the rest of the session. State the assumed level once on the first card ("assuming you know the Flipr/Citrus split — say so if not"), then fade scaffolding silently.

## Mid-flow input

- **New link/material:** acknowledge in one line and decide *loudly* whether it changes the verdict ("that thread confirms card 3 — no change" / "this moves the timeline — card 4 is now wrong, fixing it"). Never absorb silently.
- **Contradiction:** integrate, state the delta, offer to re-fork or fold in. Do not defend, do not cave reflexively, do not grovel ("you're absolutely right"). If the user is wrong, say so with the evidence — critical partner, not yes-man.
- **Tangent:** answer as a one-off card marked `[detour]`, push the map position onto a stack, then offer `back to <N>`. Never lose the user's place.

Invariant: the user never loses their place, and the verdict is never silently mutated.

## Sources card

Rank by how load-bearing each source is, not alphabetically. Label the structural one: "if this is wrong, the verdict flips: <link>." Knowing which evidence is structural vs corroborating is worth more than the list.
