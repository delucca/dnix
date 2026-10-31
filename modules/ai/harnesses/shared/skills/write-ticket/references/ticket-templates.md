# Ticket templates

Copy-paste starting points. Fill every field; delete lines that genuinely don't apply. Keep the title specific and searchable. Use `<needs input: …>` for facts you don't have — never invent them.

---

## Story (user-facing value)

```md
Title: <verb-led, specific outcome + component>

Why (context):
<the user pain or business reason — the problem, not the solution>

What (outcome):
As a <role>, I want <goal> so that <benefit>

Acceptance criteria:
- [ ] Given <context>, when <event>, then <observable outcome>
- [ ] <or a plain testable bullet>

Out of scope (non-goals):
- <explicit exclusion>

Links: <design / doc / related tickets / SME contact>
Size: <estimate or T-shirt>
```

## Task / chore (technical, no user sees it)

Do not wrap technical work in a fake user story. Use FDD phrasing.

```md
Title: <action> the <result> for a <object>   e.g. "Add retry with backoff to the payments client"

Why (context):
<what this enables or unblocks; link the parent story if there is one>

Acceptance criteria:
- [ ] <testable technical condition>

Out of scope: <explicit exclusion>
Links: <parent story / doc>
Size: <estimate>
```

## Bug

Centered on reproduction. Severity and priority are separate fields (see quality-checklist.md).

```md
Title: <symptom> + <where>   e.g. "Checkout total wrong when cart has >10 items (web)"

Environment: <OS / browser+version / device / build or commit hash>

Steps to reproduce:
1. <explicit, minimal — name the exact element, not "it">
2. ...

Expected result: <what should happen>
Actual result:   <what happens — exact error text/codes, verbatim>

Reproducibility: <always | intermittent (X of Y attempts) | once>
Severity: <technical impact: blocker/critical/major/minor/trivial>
Priority: <urgency to fix: P0/P1/P2/...>
Evidence: <logs / stack trace / screen recording / HAR / crash id>
Regression: <last known-good version, if known>
```

For code-level bugs, prefer a **minimal reproduction** (smallest self-contained failing example) over prose — it removes the reproduction burden from the fixer and is the single biggest accelerant to a fix.

Security vulnerabilities are the exception to "share everything": report privately to the owner first, not in a public tracker before a patch. Do not paste full exploit detail into an open ticket.

## Spike (timeboxed investigation)

```md
Title: [SPIKE] <the question to answer>

Question: <the decision this unblocks>
Timebox: <e.g. 2 days>
Done when: <the artifact — a recommendation / prototype / estimate>
Links: <the story this de-risks>
```

## Epic (large outcome — keep thin)

```md
Title: <the outcome / capability>

Goal: <what is true for the user when this is done>
Success metric: <how we'll measure it>
In scope: <the coherent set of stories this covers>
Out of scope: <what this epic deliberately excludes>
```

Refine an epic into stories over time. Do not pre-specify every child up front, and never let it become a permanent "misc / tech-debt / Q3 bugs" bucket.

## Shape Up-style pitch (for larger bets, before stories exist)

```md
Problem:      <a concrete story motivating the work>
Appetite:     <the fixed time budget — decided BEFORE solutioning>
Solution:     <shaped at low fidelity: breadboard / rough sketch, not full spec>
Rabbit holes: <named risks / complexities to avoid>
No-gos:       <explicitly out of scope>
```

The power move is "appetite first, scope variable" — it is the strongest defense against scope creep.
