# Report format

The source of truth for the report comment's shape, rules, and rendering. One skeleton, two variants: only the first line and the closing sections differ. A stable shape lets ticket watchers scan on autopilot.

## Progress variant

Use while work continues on the ticket.

```
**Status:** On track | At risk | Blocked — <one sentence answering "should I be worried?">

**Done:**
- <specific outcome> ([artifact](url)) — <what it enables, one clause, only when not obvious>
- <specific outcome> ([artifact](url))

**Found/Decided:** (include only if something notable surfaced)
- <finding or decision> ([evidence](url))

**Next:** <concrete next action, with owner when it isn't you>
**Blocked:** (include only when blocked) <what, on whom, the specific ask, since when>
```

## Final variant

Use when the work is merged and verified and the ticket is about to be resolved. This comment is what a future reader finds when they open the closed ticket; it states outcomes so nobody re-derives them.

```
**Status:** Done — <one line: what shipped>

**Done:**
- <outcome> ([artifact](url))

**Verified:** <how it was checked: test run, staging link, dashboard, experiment readout>
**Follow-ups:** <tickets filed for deferred work, or "none">
```

## Rules

1. **First line is the verdict.** A reader who stops there knows the state and whether to worry.
2. **Hard cap ~120 words / 10 lines.** Overflow belongs in the ticket description, a doc, or a sub-task — link it instead.
3. **No link, no claim.** Every done-item carries its artifact inline (PR, diff, commit, dashboard, doc), placed where the claim is made — a bottom link dump forces the reader to re-match links to claims.
4. **Past tense, active voice, named actors.** "Merged X", "Waiting on @name for Y" — never "it was decided".
5. **Be countable.** Keys, numbers, names, versions. "Made progress", "various fixes", and "mostly done" say nothing.
6. **Bold labels + bullets only.** No headings (they render oversized in comment threads), no tables, no nested lists.
7. **Write for the absent reader.** Enough context that someone picking the ticket up cold can continue without asking.
8. **Blockers name the unblock.** What is needed, from whom, since when — "blocked on infra" helps no one.
9. **No ETA unless the user gave one.** A slipped ETA costs more trust than none; when useful, commit to when the next update lands.
10. **Say why only when it isn't obvious.** One clause of impact ("unblocks the ranking rollout"), not a paragraph of background.
11. **Omit activity theater.** Meetings held, "synced with", methodology, restating the ticket description.
12. **Decisions flow to the description.** A comment recording a decision prompts a reminder to update the ticket body; comments get buried.
13. **One comment per meaningful state change**, not per work session; never repeat a prior update.
14. **Final comments state how the work was verified**, not just that it is done.

## Anti-patterns — never in a report

- Wall of text; a narrative of the journey ("first I tried X, then...")
- Vague progress ("moving along nicely", "almost there")
- Claims without links; link dumps at the bottom
- Passive voice hiding ownership ("it was determined")
- The verdict buried below the fold
- Activity or metric dumps unrelated to outcomes
- Reflexive ETAs
- Hype and AI filler: "it's important to note", "leverage", "seamlessly", "significantly enhanced", exclamation marks, emoji, em dashes
- Euphemisms ("resource challenges" for "we're short one person")

## Jira wiki rendering

Jira comment bodies are **wiki markup** — not markdown, not ADF. Unconverted markdown posts as literal asterisks and brackets. Convert the approved draft:

| Markdown draft | Jira wiki markup |
|---|---|
| `**bold**` | `*bold*` |
| `[label](url)` | `[label\|url]` |
| `- item` | `* item` |
| `` `code` `` | `{{code}}` |
| `@someone` | `[~username]` |
| `# heading` | never used in comments |

`*Status:*` at line start renders bold (no space after the asterisk); `* ` with a space renders a bullet.

## Worked example (progress variant, Jira rendering)

```
*Status:* On track. Token refresh fix is merged; rollout config is next.

*Done:*
* Merged the token-refresh fix ([PR 1234|https://github.com/example/repo/pull/1234]). Unblocks the masthead rollout.
* Added integration coverage for the expiry edge cases ([PROJ-142|https://jira.example.com/browse/PROJ-142]).

*Next:* Stage the rollout config. Next update lands Friday.
```

Contrast with what it replaced: "Made good progress this week on the auth work, had some productive syncs, and things are mostly done — will share links soon." No verdict, no links, nothing countable.

## Sources

Condensed from: Atlassian Community "How to write a useful Jira ticket" (Absent-Factor; when a comment is warranted), Lullabot "The Art of Jira" (decisions flow back to the description), The Cranky PM on status updates ("should I be worried?" first line; activity theater), Recapline's weekly status template (pair every key with what it enables), the PPP framework, Atlassian Statuspage incident-comms guidance (ETA discipline), and opensource.guide maintainer practices (closing summaries).
