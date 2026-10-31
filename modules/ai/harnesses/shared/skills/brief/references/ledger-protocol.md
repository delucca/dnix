# Ledger protocol

State lives in one markdown file per session. A skill is re-invoked each turn against a context window the harness will summarize or truncate — so continuity cannot live in memory. The ledger is the spine; treat the model as a stateless reducer over it. `glance` weight skips all of this.

## Paths

```
~/.agents/output/brief/<slug>/ledger.md     ← source of truth (state + decisions + claim rows + progress)
~/.agents/output/brief/<slug>/materials/    ← copies of provided files, fetched pages
~/.agents/output/brief/<slug>/findings/     ← raw sub-agent output, one file per engine (write-to-file)
~/.agents/output/brief/<slug>/eval.md       ← evaluation notes when they outgrow the ledger
```

`<slug>` = `YYYY-MM-DD-<kebab-of-demand>` (e.g. `2026-06-05-jp-masthead-cta-options`). Build it with `date` + a short kebab of the demand. Create dirs with `mkdir -p`.

## Reconcile loop (every turn)

1. Resolve the slug: `--resume <slug>`; else if a recent ledger plausibly matches the demand, offer to resume; else start new.
2. If a ledger exists, **Read it first.** It overrides in-context memory — the harness's own summarization is exactly what produces stale memory, so deliberately distrust what you "remember" and trust the file.
3. Determine `phase` and `Next card` from the ledger, not recollection.
4. Act.
5. **Write the ledger before yielding:** update `phase`, `updated`, explain-back progress checkboxes, any new decision or constraint. End the turn with a one-line self-check that the ledger matches what you just said.

## What the ledger holds — and does not

Holds: the demand restatement, scope question, weight, scenario, lens, plan + approval, decisions/constraints, the claim ledger rows, a **findings index of pointers**, and explain-back progress.

Never holds raw findings. Inlining sub-agent output bloats the ledger, makes re-reading it each turn expensive, and recreates the context problem on disk. **Ledger = index + state + decisions. Content lives in `findings/`.** When explaining a card, Read only the one findings file it needs.

## Resume

On `--resume <slug>` (or "continue the masthead brief"), glob `~/.agents/output/brief/*/ledger.md`, pick by slug or most recent, Read it, and replay from `phase` + `Next card`. Because findings are on disk and pointed to from the ledger, the original context is not needed — a new session days later continues mid-explanation correctly.

## Lazy evaluation

Evaluate and verify a claim only when about to explain the card that rests on it. This couples cost to the user's actual curiosity, not corpus size — on a `deep` demand most findings are never drilled into, and eager verification of the whole fan-out is wasted.

## The ledger is a control surface

It is plain markdown at a known path, so the user can open it, fix a wrong decision, or reorder the explain-back plan; the next turn's reconcile picks it up. Inspectable, correctable state is a feature — surface the path when it helps.
