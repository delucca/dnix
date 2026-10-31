# Routing — scenario detection, engines, degradation

Decide where to investigate and where to land, by capability first and content second.

## Detect the scenario

1. **Capability (authoritative).** If no internal-investigation skills or agents are listed on this machine, you physically cannot route there — treat the scenario as `public` regardless of content. This is free and decisive.
2. **Content signals.** Internal hostnames, Phabricator `D<digits>`, internal code hosts, tracker project keys → `internal`. Public domains, personal accounts, consumer products → `public`. Both present → `mixed` (tag each finding by origin).
3. **Form factor is a weak tiebreaker only.** A work devbox leans internal, but work laptops run personal demands constantly. Never gate on form factor alone.

## Route by scenario

| Scenario | Investigation engine | Knowledge (check first) | Landing |
|---|---|---|---|
| internal | an internal-investigation skill for internal claims and root cause; an internal per-domain researcher agent to explore one domain; `research` for external | `bilbo:recall`, an internal search skill | `bilbo:note` |
| public | `research` | `bilbo:recall` | `bilbo:note` |
| mixed | both engines, findings tagged by origin | both | per-finding |

Lens-specific reads during investigation (internal, via whichever gateway skills are installed): a chat-reading skill (thread reconstruction for decode-thread), a document-reading skill (provided docs and sheets), a code-search skill (verify a load-bearing code claim), an internal search skill (broad "what do we have on X" sweep), `use-chrome` (render a live page that needs JS).

## Degradation contract

When the scenario is `internal` (by content) but the internal engines are unavailable (by capability):

- Route to external `research` and read the provided materials directly.
- Write a ledger constraint line: `C: internal tools unavailable on this host — internal evidence not searched`.
- **Disclose it in the briefing**, in the verdict's confidence, not a footnote: "findings are from the materials you gave me plus public sources; I could not search internal systems from this machine."

Honest degradation beats a silent fallback that the user reads as a complete internal investigation.

## Internal lateral reading

External lateral reading (checking a source against what others say about it) is impossible for a PRD, an internal doc, or a chat thread. Substitute **system-of-record corroboration**: confirm the doc against the live system it describes (a config lookup for config, a code-search skill for code), and prefer the system of record over the doc describing it. Internal docs go stale silently — a doc's claim about "current rollout" is unverified until checked against the runtime. See the reliability model in `investigation-playbook.md`.
