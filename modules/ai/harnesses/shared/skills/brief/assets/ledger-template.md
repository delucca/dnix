# Brief session: <demand title>
slug: <YYYY-MM-DD-kebab-demand>
weight: standard            # glance | standard | deep
scenario: internal         # internal | public | mixed  (drives tool routing)
lens: decode-thread        # evaluate-artifact | decode-thread | trace-behavior | get-up-to-speed | decision-help | explain-only
phase: explain-back        # frame | plan | investigate | explain-back | landed
updated: <ISO-8601 timestamp>

## Demand (as understood)
<one paragraph: what was actually asked + the decision it informs>

## Scope question
<the single question this session must answer>

## Plan  [APPROVED <ts>]   # omit the tag until approved; omit the whole section for ungated runs
- Strategy: <how this gets answered>
- Engines: <research(deep) / internal investigation / internal domain researcher / materials-only>
- Hypotheses to test: <H1; H2; H3>

## Decisions & constraints
- D1: <decision> [user-confirmed | inferred]
- C1: <constraint, e.g. internal tools unavailable on this host>

## Claim ledger
| # | claim | type | support | load-bearing |
|---|---|---|---|---|
| 1 | <falsifiable claim> | fact/judgment/inference/assumption/marketing | corroborated/single/contested/unverified | yes/no |

## Findings index   # pointers only — never raw content
- F1 → findings/research-<topic>.md   [confidence: Likely]
- F2 → findings/internal-<topic>.md    [Provisional — 1 citation unverified]

## Explain-back progress
- [x] Card 1: <title> — delivered, acknowledged
- [ ] Card 2: <title> — next
- [ ] Card 3: <title>
Open checkpoints: <none | the fork awaiting the user>
Next card: <title>

## Parking lot
- <tangent noted, not chased>
