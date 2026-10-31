# Troubleshooting

Failure handling for the brief pipeline. Default posture: present what you have, label the gap, never fabricate.

## An engine fails or returns nothing
Present partial findings with the gap marked. Offer to retry with a narrower brief, switch engines (`research` ↔ an internal-investigation skill), or proceed on materials alone (disclosed). Do not stall waiting for a perfect investigation.

## Investigation finds nothing
Say so plainly: "I could not find evidence on X." Never manufacture a finding to fill the slot. A clean "unknown" is a finding; a fabricated one is a trust collapse.

## A citation will not verify
Demote the claim to `unverified` / Provisional, label it a lead, and hedge in speech ("the research agent claims this but I could not confirm the source"). Never inherit a sub-agent's citation as corroborated.

## Internal tools unavailable but the demand is internal
Degrade to external `research` + provided materials. Log `C: internal tools unavailable on this host`. Disclose in the verdict's confidence line. See `routing.md`.

## The user goes quiet
The ledger persists; nothing is lost. The session is resumable later with `--resume <slug>`. No action needed.

## Ledger / context divergence (the insidious one)
If your in-context memory and the ledger disagree, the ledger wins — read it first, every turn. Symptoms: you narrate "we're on card 3" but the ledger says card 1, or you re-decide something the user already corrected. Mitigation: keep the ledger small (pointers, not content) so re-reading it stays cheap, and write it before yielding so state never lags speech.

## The demand turns out to be a single lookup
Stop the pipeline. Name the direct tool ("this is a one-shot lookup — run the config lookup directly") and exit. Pipeline ceremony on a lookup is the fastest way to feel heavy.

## Scope balloons mid-session
A `glance` that becomes a `trace` is a re-classification, not a silent expansion. Say "this is bigger than it looked — promoting to deep, which means a plan gate", and re-enter Phase 1.
