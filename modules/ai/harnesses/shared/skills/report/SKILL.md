---
name: report
description: Drafts a link-backed status report from session and git evidence and posts it on the originating ticket after approval. Use for report on the ticket, update PROJ-123.
argument-hint: "[ticket-id or URL] [optional focus notes]"
disable-model-invocation: true
allowed-tools: Bash(uv run:*), Bash(git *), Bash(gh *), Bash(cat *), Read, Write, Skill, AskUserQuestion
---

# Report

Post one short, objective, evidence-linked report comment on the ticket that originated the current work: the current state, what was done with a link per claim, and what happens next. The draft is humanized, previewed, and posted only after the user approves the exact text.

## When NOT to use this skill

- Drafting or improving a ticket body — use `write-ticket`.
- Any other ticket write (transition, assign, edit fields) — the plugin `use-jira` gateway only reads and comments; those other writes go through `atlassian-mcp` directly. This skill posts comments, nothing else.

## Step 1 — Identify the ticket and tracker

Resolve the target ticket, in this order:

1. `$ARGUMENTS` contains a ticket key, issue number, or URL — use it. Anything after the ticket reference is focus notes: emphasis the user wants in the report.
2. The current branch encodes it. Branches typically follow `<user>/<TICKET-ID>-<short-desc>`; run `git branch --show-current` in the work's repo or worktree and extract the ID.
3. The conversation names the ticket the current work came from.
4. None of the above — ask the user for the ticket. Never guess a key; a report on the wrong ticket misleads two teams at once.

Then classify the tracker:

- Shape `ABC-123` (`^[A-Z][A-Z0-9]+-[0-9]+$`) — **Jira**. Browse URL: `<jira-host>/browse/<KEY>`, from the Jira tool's configuration or the ticket link.
- GitHub issue/PR URL, `#N` in a repo with a GitHub remote, or `owner/repo#N` — **GitHub**, via `gh`.
- Ambiguous — ask, offering both readings.

For Jira, use the Jira tool the session has (an MCP server or CLI); if none is available, stop and tell the user. Confirm auth before doing anything else by fetching the issue, which doubles as Step 2's fetch. A 401/403 means the user must re-authenticate; stop and tell them. Do not retry-loop.

## Step 2 — Read the ticket and set the watermark

Fetch the ticket and its comments:

- Jira: the issue fetch from Step 1 for the issue itself; the Jira tool's comment listing for comments (page through if needed). Route large results to a file and read the file, not a truncated preview.
- GitHub: `gh issue view <N> --comments` or `gh pr view <N> --comments`.

From what comes back, capture:

- **Watermark** — the most recent prior update comment (yours or a teammate's status report). The new report covers only work after it; re-reporting double-counts and misleads the reader.
- **Ticket state** — current status and summary, to sanity-check the verdict line (don't post "Done" on a ticket someone reopened an hour ago).
- **Audience** — who is watching the ticket, so the report reads for them, not for you.

## Step 3 — Gather the evidence

Every claim in the report must trace to an artifact. Collect, in order of signal:

1. **This session** — the work usually just happened here. Pull the concrete outcomes, decisions, and verification results from the conversation.
2. **Git** — in the work's repo or worktree: `git log --oneline <base>..HEAD` and `git diff --stat` for what actually changed since the watermark.
3. **Review artifacts** — PR URL via `gh pr view --json url,title,state`, or the Phabricator diff link if the session produced one.
4. **Verification** — test runs, staging links, dashboards, experiment readouts mentioned in the session.

Build a claim-to-link map. A claim with no artifact either gets dropped or becomes honest wording ("no material progress since the last update"). Never pad.

## Step 4 — Draft the report

Read `references/report-format.md` and follow it: pick the variant (**progress** while work continues, **final** when the work is merged/verified and the ticket is about to be resolved), fill the skeleton, and obey every rule in it. Draft in markdown with bold labels and bullets. Weave the user's focus notes from Step 1 in.

The two non-negotiables, stated here because everything else in the reference serves them:

- **First line is the verdict.** A reader who stops there knows the state and whether to worry.
- **No link, no claim.** Each done-item carries its artifact inline, where the claim is made.

## Step 5 — Humanize

If a text-humanizing skill is listed, invoke it on the draft via the `Skill` tool, instructing it to:

- keep the source language (these tickets are in English; don't default to PT-BR),
- preserve the label lines (`**Status:**`, `**Done:**`, ...), every link, and the bullet structure — humanize only the prose,
- keep plain ASCII punctuation; tracker comments are no place for decorative characters.

If no such skill is listed or it errors, do not hand-write a "humanized" version. Label the draft not-yet-humanized in the preview and let the user decide whether to post it as-is.

## Step 6 — Render for the tracker

- **GitHub** — the markdown draft posts as-is.
- **Jira** — convert to Jira wiki markup using the table in `references/report-format.md` (`*bold*`, `[label|url]`, `* ` bullets, `{{monospace}}`, `[~username]` mentions). The comment endpoint takes wiki markup, not markdown and not ADF; unconverted markdown posts as literal asterisks and brackets.

Never use headings in either rendering. In a comment thread they shout; bold labels scan just as well at normal size.

## Step 7 — Preview and approve

Show the user the exact final body that will be posted (the rendered version, not the markdown source). Use `AskUserQuestion`: **Post** / **Revise** (take their edits, re-run Steps 5-6 on changed prose) / **Cancel**.

Posting without the user approving this exact text is the one unrecoverable failure of this skill — the comment lands in front of the whole ticket audience.

## Step 8 — Post and confirm

Write the approved body to a temp file first — it is multi-line and quoting it inline breaks:

- Jira: `Write` the rendered wiki-markup body into a file, then post it as a comment on the issue with the Jira tool, without automatic retries — this call is not idempotent.
- GitHub: `gh issue comment <N> --body-file /tmp/report-comment.txt` (or `gh pr comment`).

Then confirm to the user with the ticket link. If the report records a decision, remind the user to fold it into the ticket description — decisions buried in comments get lost (this skill never edits the description itself).

If the post fails, show the error and keep the approved body visible so it isn't lost. One retry at most, then stop and report.

## Failure modes

- **Jira auth fails** (401/403) — tell the user to re-authenticate; stop with that message. No retry loops.
- **No ticket identifiable** — ask. Never post to a guessed key.
- **No post-watermark evidence** — draft the short honest variant ("no material progress since <date>; next: <action>") and still preview it. Silence on a stalled ticket is worse than a modest update.
- **No humanizing skill, or it errored** — preview the raw draft, labeled as such; user decides.
- **Post request fails** — surface the error with the body preserved; one retry, then stop.

## References

- `references/report-format.md` — the two template variants, writing rules, anti-pattern list, Jira wiki conversion table, and a worked example. Load it at Step 4; it is the format's source of truth and is not duplicated here.

## Hard prohibitions

- Never post without the user approving the exact final text in this session. `disable-model-invocation` guards entry; the Step 7 preview guards exit.
- Never make a claim without an artifact link. Unverifiable claims erode the ticket as a record.
- Never fabricate progress, metrics, or verification results. Thin evidence means a short honest update, not padding.
- Never state an ETA the user didn't give. A slipped ETA costs more trust than none; commit to the next update instead.
- Never use headings or tables in the comment. Bold labels and bullets only.
- Never re-report work already covered by a prior update comment.
- Never write anything but a comment: no transitions, no field edits, no assignments, no description changes.
- Never loop on auth failures; one smoke test, then escalate to the user.
