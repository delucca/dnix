# Investigation playbook

The truth-finding engine. The spine is a **claim ledger**: the few falsifiable claims the answer rests on. Everything else is operations on it. Concentrate rigor on rows that are both load-bearing and weakly supported; ignore the rest.

## 1. Frame the decision before reading sources

Write one line: *the decision this feeds, and how the answer changes the user's action (A vs B).* Reading the user's materials before framing the question is how you absorb their framing. If you cannot write the line, ask one question.

## 2. Triage the provided materials (before going external)

For each item: type (primary / secondary / marketing / opinion / data), currency, authority, and whether the author has an interest in the conclusion. Marketing tells: no named author, corporate byline, no method, no date, conclusion favors the publisher.

Then emit a 3-line triage as part of the first visible output:
- What kind of source each is.
- **The shape of the gap**: e.g. "these all argue *for* X; nothing here could show X is wrong." Say this even when it is uncomfortable — it is the framing-bias detector.
- Whether the materials are sufficient on their own.

### Sufficiency vs expansion

Declining to research is often the most valuable move. **Materials are enough** when: the question is internal-policy-bound (what does *our* doc/config/owner say); the sources are primary and authoritative for the question; claims are uncontested and the decision is reversible; or the ask is "help me understand/structure," not "is this true." Say so and stop going external.

**Must corroborate or expand** when: a load-bearing claim is single-sourced to an interested party; the materials agree suspiciously and none could falsify the thesis (go find the disconfirming view on purpose); a load-bearing number or quote needs tracing to origin; or the decision is irreversible / high-blast-radius (raise the floor).

## 3. Build the claim ledger

Extract discrete, falsifiable claims (a claim is checkable: "X reduced Y by 23% in a 2024 RCT", not "X is great"). For each:

```
CLAIM | TYPE (fact/judgment/inference/assumption/marketing) | SUPPORT (corroborated/single/contested/unverified) | LOAD-BEARING? (does the conclusion break if this is false?)
```

Decide what to research from the ledger's gaps — the load-bearing-and-weak rows — not from a generic "go learn the topic" impulse.

## 4. Lateral reading (external) and system-of-record (internal)

External: do not read deeper — go sideways. Search what independent third parties say about the source, the author, the funding, the statistic's origin. Trace numbers and quotes to where they were first said.

Internal (lateral reading is impossible): reliability ≈ **owner authority × confirmed-against-system-of-record × speech-act weight**.
- **Owner authority:** is this the owning team's artifact, or a downstream team's interpretation?
- **System of record:** confirm the doc against the live runtime; prefer runtime over doc; treat "current state" claims as unverified until checked.
- **Speech-act (Slack):** a decision ≠ a proposal ≠ thinking-out-loud ≠ a vent. Mark which.

## 5. Brief sub-agents to break the thesis

Never hand a sub-agent the broad topic. Hand it a specific claim to confirm or break, and what would count as disconfirmation. Three rules:
1. Ask for the **strongest disconfirming evidence** and the owning team's disagreement, not supporting material.
2. Demand **origins, not summaries** — primary source URL + exact quote per claim.
3. Run depth **low first** (quick to map the terrain), escalate only on rows still load-bearing and unresolved. Exhaustive-by-default is the biggest time sink and rarely changes the decision.

## 6. Verify returns before trusting them

A sub-agent's confidence is not evidence. Never promote SUPPORT to `corroborated` on a sub-agent's say-so. Promotion requires either: you opened the primary source yourself (`use-chrome` / `WebFetch` / the doc tool / a code-search skill, if installed) and saw the claim, or two **independent origins** (judged by tracing, not counting — ten restatements of one study is one source). Verify **lazily**: only the load-bearing claims the user actually drills into. Unverifiable claims stay `unverified` and are labeled as leads, not facts.

Watch sub-agent **independence**: if all fan-out workers hit the same blog ecosystem (external) or the same copy-pasted wiki page (internal), their agreement is one source wearing many hats.

## 7. Competing hypotheses (when sources disagree)

Lightweight, no full matrix. List the 2–3 explanations. For each, ask **"what does this have to explain away?"** The leading hypothesis has the **fewest** things to explain away, not the most cheerleaders. Then **steelman the one the user (or their links) liked least** in one paragraph. A weak steelman is a real result and a confidence boost; a strong one the user needs before acting. Note the one fact that, if wrong, would flip the conclusion.
