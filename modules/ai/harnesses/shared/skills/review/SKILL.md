---
name: review
description: Deep multi-agent code review that fans out lenses and verifies every finding. Use for "review this", "deep review", "review PR 123", "review D456". NOT for the pre-push gate (review-and-push).
argument-hint: "[pr N | D123 | branch | staged | working | since REV | A..B] [model, lens=/verify= overrides, no-audit]"
allowed-tools: Bash, Agent(general-purpose), Read, Write, Grep, Glob
---

# Review

## Goal

Produce a code review whose every finding is grounded in something checkable - a library source
passage, a fetched URL, or an explicitly labeled judgment call - by routing the change to the
library sources that cover its concerns, fanning out independent review lenses over deliberately different inputs,
and putting every candidate finding through an adversarial verification gate before it reaches
the report.

Read-only against the repository: never edits its files, commits, pushes or posts. It writes to the
session scratchpad, and runs the project's code only in a throwaway clone under the scratchpad, only
on the user's own code: mutation (Step 3) and a refuter's disproving check (Step 7). That code can
still fill `$HOME` caches and reach the network.

## When NOT to use this skill

- **Committing and pushing behind a quality gate** — use `review-and-push`; its gate delegates
  here, so both paths run the same engine.
- **Understanding what a change does** — use `explain`. This skill judges; `explain` teaches.
- **A quick single-pass opinion on a small diff** — the built-in `code-review` is one agent and a
  fraction of the cost.

## Terms

- corpus - one corpus of bilbo's library, listed by `bilbo library` and described by its guide,
  `bilbo library <corpus>`: one `##` entry per source, a facts line (file, id, size, tokens,
  headings, sometimes `catalog`) and two or three sentences on what it covers. Found by name, else
  through `bilbo recall --library` (this skill has no Skill tool, so it runs the `bilbo` CLI
  itself, the way the `bilbo:reference` skill does).
- `<scratchpad>` — this session's scratchpad directory.
- tripwire - a deterministic detection (a deleted test, a skipped test, a loosened gate, a
  suppression) that goes straight to the refuter as a candidate.
- pointer - a ranked fact (a complexity increase, a duplicate block, an uncovered line) that steers
  a lens and is never a finding on its own.
- unmeasured - a check that could not run. It is never reported as clean.
- extra lens - a lens brief installed under `~/.config/ai/review-lenses/`
  (`references/lens-briefs.md`).
- throwaway clone - the local clone under the scratchpad where the project's code may run
  (`references/mutation.md`).

Subagents get a fresh cwd and no shell expansion of `~`. Expand every path to an absolute one
before putting it in a delegation prompt.

## Evidence trust labels

Every claim carries exactly one label, and the labels never blend:

- `bilbo:<id>#<heading> "<quote>"` - a passage of a library source, cited by the source id, the
  heading path it sits under and a verbatim quote of at least six words from that section.
- `code: <path>:<line>` - a line of code someone actually read.
- `web: <URL>` — external evidence someone actually fetched.
- `judgment` — engineering judgment with no external grounding.
- `metric: <check> <file>:<line> <detail>` - a deterministic measurement from `diff-metrics`, quoted
  exactly, such as `metric: complexity src/parse.py:10 parse 4 -> 9 (changed)` or
  `metric: mutant src/parse.py:31 survived (replaced < with <=)`. A metric is evidence of what is
  there, not a target.

Dressing judgment as a citation is the failure this skill exists to prevent: a review is only
worth its evidence, and the report has to state what was actually read rather than what was
configured.

## Workflow

### Step 1 — Parse arguments

Run `cross-audit harness` (when it is not on PATH, `python3 -I ~/.config/ai/common/skills/review/scripts/cross_audit.py harness`)
and state the answer: `claude`, `codex`, `agy` or `unknown`. The harness decides how lenses are
spawned, which models are the default and which auditors run in Step 7b.

If this session has no spawning tool for its harness (the table below), stop now, before any work:
print `review: cannot run here - no tool to spawn lenses` and end with no Verdict line. A subagent
whose `tools` omit `Agent`, or a session at the depth limit, lands here. Never report a clean
review that did not run.

Tokenize `$ARGUMENTS` on whitespace. A `repo=<dir>` token names the repository to review: every git and
`diff-metrics` command then carries `-C <dir>` or `--repo <dir>`, `<toplevel>` below means that
repository's toplevel, and no `cd` is used (the shell's directory does not persist between calls).

**Model tokens.** A bare model token sets every role. A `lens=<model>` or `verify=<model>` token
sets that one role. Later tokens override earlier ones. A token must name a model this harness can
spawn: `opus`, `sonnet` or `haiku` on Claude Code, a model id such as `gpt-6-astra` on Codex, a tier
(`pro`, `flash`, `flash_lite`, `inherit`) on agy. A token for another harness's model, or an unknown
one, gets a one-line statement of the grammar and a question - never a guess. A Fable model is
refused outright. The token `no-audit` skips Step 7b.

| Harness | Spawn lenses and refuters with | Default `lens` and `verify` | The report names |
|---|---|---|---|
| Claude Code | `Agent` (`general-purpose`), `model: opus` | Opus 5.5 | `opus` |
| Codex | `spawn_agent` with `gpt-6-astra` and high effort when the tool takes a model, else `cross-audit spawn --harness codex` per lens | gpt-6-astra, high | `gpt-6-astra (high)` plus `via spawn_agent` or `via codex exec` |
| agy | `invoke_subagent` with model `pro` | agy's pro tier | `pro (gemini-4-argon)` |
| unknown | whatever agent tool the session has, no model argument | the session's model | `session model (harness unknown)` |

The defaults are each harness's high-reasoning model, the user's choice.

The same grammar drives `orchestrate`, so the two surfaces stay interchangeable. Effort is not
part of the grammar; harness defaults apply.

**Target tokens.** Everything left names the target, first match wins:

| Tokens | Target |
|---|---|
| `pr <n>`, a GitHub PR URL | GitHub pull request |
| `D<digits>`, `diff <id>` | Phabricator revision |
| `staged` | index vs HEAD |
| `since <rev>` | everything since REV: committed, staged, unstaged, untracked |
| `working` | `since HEAD` |
| `branch` | current branch vs the default branch |
| `<A>..<B>`, `<A>...<B>`, a single ref | that range, that commit |
| *(none)* | dirty tree → `working`; clean tree → `branch` |

### Step 2 — Resolve the target

Load `references/source-commands.md` for anything other than a plain local diff — it holds the
verified git semantics, the `gh` field list and its pagination caps, and the Conduit call chain.

Local targets come from `diff-metrics diff`, which pins the git output knobs so the result is a
patch even under an external diff tool; `references/source-commands.md` has the flags per target.
For `working`:

```bash
diff-metrics diff --repo "$toplevel" --base HEAD --worktree > "$scratchpad/review/target.diff"
```

Never hardcode `main`; resolve the default branch through the chain in the reference file. The
reference also holds why `branch` diffs the merge base against HEAD and not the working tree. For
`branch`, also collect `git log --oneline "$default"..HEAD`, and for `since REV`
`git log --oneline REV..HEAD`: the commit messages are the claimed behavior that the tests lens
checks against.

- A remote fetch tool that is missing or unauthenticated is a hard stop: report exactly what
  failed. Substituting a local diff for a PR silently reviews the wrong code.
- An empty diff stops the run. There is nothing to review.

Write the resolved unified diff to `<scratchpad>/review/target.diff`. Lenses receive absolute file
paths, not inlined diffs; the diff is then paid for once instead of once per agent, and each lens
keeps its context for its own evidence. First delete the last run's state (`<scratchpad>/review/mutation`,
`audit`, `mutants.txt`, `candidates-*`, a `coverage.path` whose hash is not this diff's), keeping a handed-in `metrics.json` and `claim.txt`. For a local
target, record `diff-metrics fingerprint --repo <toplevel>` now: Step 8 compares it with a second one.

### Step 3 — Measure the change

Load `references/metrics.md`.

**3a, metrics.** Use `<scratchpad>/review/metrics.json` only when every identity field in the
freshness rule matches (diff sha256, repo, base, head, schema). Otherwise run `diff-metrics measure`
with the target's flags (the table in `metrics.md`), plus `--coverage <file>` when
`<scratchpad>/review/coverage.path` names a file whose recorded `diff-sha256` is this `target.diff`'s, and say "stale metrics.json
ignored" when one was there. A remote target without both commits local gets no base flag, and only the diff-only
checks run. **S** is `facts.S` and **F** is `facts.F`, with lockfiles, vendored trees, generated
files and binaries already excluded; name `facts.excluded` in the report. Then run
`diff-metrics bundle --metrics <scratchpad>/review/metrics.json --diff <scratchpad>/review/target.diff --dir <scratchpad>/review`.

If S < 10, say that the floor is Correctness plus one refuter, and that triggered lenses add to it.
Offer the built-in `code-review` as the cheap alternative, then proceed unless redirected.

**3a, the claim.** Read any `<scratchpad>/review/claim.txt` first. Its body is the caller's claim
only when line 1 is `diff-sha256: <this hash>`. Then always rewrite the file: line 1
`diff-sha256: <this hash>`, then `## Caller's claim` (the valid handed-in body, or "none"), then
`## From the target` (commit messages from `git log --oneline` over the target's range, the PR title
and body, or the revision summary, or "none"). Every lens that names `claim.txt` reads this file,
and "a caller handed in a claim" means the first section is not "none".

**3b, mutation.** Follow `references/mutation.md`, on the user's own code only. It produces
`mutants.txt`, a status line for the report header, and the throwaway clone, which lives until
Step 7b ends. Run `timebox`, `cross-audit run` and `cross-audit spawn` in the background with an
explicit timeout under the harness's tool cap and wait for them (Claude Code: Bash with
`run_in_background`). A foreground command killed at the tool timeout cannot be cleaned up after
SIGKILL, and a SIGTERM makes both scripts kill their children and still write their summary.

### Step 4 — Route to library sources

Standards live as sources in bilbo's library, one corpus per topic, discovered at runtime, never
hardcoded: the corpora grow and a stale list would send lenses to grounding that no longer exists.

Derive the **concerns** from the diff and select **at most 4**, relevance-ranked:

1. **Languages** - map changed-file extensions to language names (`.go`, `.rs`, `.swift`, `.hs`,
   `.clj`, `.el`, `.rkt`, `.scm` and whatever else the diff holds). Only languages with meaningful
   changed lines qualify; a one-line config bump does not summon a style guide.
2. **Cross-cutting concerns** - triggered by content and paths rather than extensions:
   - architecture: F >= 5 across >= 2 modules, or new public interfaces or services, or code moved
     between layers, or a new dependency. This is also the architecture lens trigger.
   - agent engineering: the diff touches agent, skill, prompt, or LLM-API code (`SKILL.md`,
     `AGENT.md`, prompt strings, model IDs, LLM SDK imports).
   - prompt engineering: the changed content *is* instruction or prompt text.
   - terminal UI: TUI frameworks and paths (ratatui, bubbletea, curses, `tui/`).
   - writing: the diff is mostly prose or `.md`.
3. **Over the cap** - rank languages by changed-line share, then the triggered cross-cutting
   ones, and drop the least-loaded. Name the dropped candidates in the report.
4. **Nothing matches, or no corpus covers any concern** - run ungrounded. Every finding then
   carries `code:`, `web:` or `judgment`, and the grounding statement says so outright. Never
   invent coverage.

Then route each concern to a corpus. By name first:

```bash
bilbo library
```

A corpus whose name or title covers the concern is that concern's corpus. When no name fits, look
the concern up by keyword, in the words its sources would use:

```bash
bilbo recall --library -- '<a term its sources would use>'
```

On exit 0 the corpora are the ones the hits' references name (`<corpus>` or `<corpus>/<name>`).
Exit 1 with `bilbo: no sources match` means no corpus covers that concern: record it under "no
coverage for" and drop it. Any other failure, or no `bilbo` on PATH, means only name routing is
available: say so in the grounding statement.

Read each chosen corpus's guide in full with `bilbo library <corpus>`; when the tool saves a long
output to a file, Read that file whole. Pick the entries that bear on this concern in this diff,
by their prose, and no others: picking is mandatory even when the whole corpus would fit, because
the picks are what the grounding statement reports. A `catalog` entry is never picked whole: pick
a section of it, `<corpus>/<name>#<heading path>`, from the hits of
`bilbo recall --library --corpus <corpus> -- '<term>'`. Record per concern the picks and the
passed-over count, then plan the reads, one plan per concern:

```bash
bilbo library plan --budget-tokens 60000 '<corpus>/<name>'...
```

It prints the plan id, `tokens:`, `partitions:` and one `partition <k>: slices <a>-<b>` line each.
A conformance lens that whole-reads gets the plan id, its slice range and the reading and citation
rules (`references/lens-briefs.md`, variant A). Then:

- **One partition**: one conformance lens whole-reads every slice.
- **Several, and S >= 10**: one conformance lens **per partition**, each whole-reading exactly its
  own partition's slices. That split buys grounding-side input diversity for free: the lenses judge
  the same hunks against *different* standards documents, which is the error independence Step 5
  rests on. The architecture lens is the exception: over a multi-partition plan it takes variant B
  (recall-grounded).
- **S < 10**: no conformance lens. The grounding folds into the Correctness prompt as variant B
  (Step 5).

**Never cover partitions partially**: reading 2 of 12 partitions and then reporting "standards
consulted" misstates the grounding, which is the one thing this skill exists to get right.

The 60000-token budget is the knob trading lens count against per-lens depth, pinned here rather
than exposed in the argument grammar. A lens's context has to hold the diff, its evidence reads,
and its grounding; ~60K for grounding leaves room for the rest, and forcing deeper reads raises
candidate recall rather than delivered quality.

### Step 5 — Select lenses and assemble inputs

Fan-out only pays when the agents fail independently, and independence comes from **different
inputs** — same-model agents re-reading the same diff with different adjectives fail together.
Assemble each bundle before spawning; load `references/lens-briefs.md` for the delegation
templates and the output contract.

**Write every bundle file to `<scratchpad>/review/` before spawning the lens that reads it.** A
lens opens the paths it is given and can produce nothing if they do not exist, so pasting a
template path without materializing the file silently guts that lens. `diff-metrics bundle` wrote
`stat.txt`, the `pointers-*.txt` files, `added.diff` and `tripwires.md` in Step 3. Per lens:

| Lens | Files |
|---|---|
| Correctness | `impact-correctness.txt`, `pointers-correctness.txt` (plus the fold slot at S < 10) |
| Conformance | `target-<language>.diff` (its language's hunks) |
| Architecture | `stat.txt`, `module-tree.txt`, `interfaces.diff`, `pointers-architecture.txt` |
| Tests & behavior | `related-tests.txt`, `claim.txt`, `pointers-tests.txt`, `mutants.txt` when mutation ran |
| Security | `security-hunks.diff`, `taint-context.txt` |
| Simplicity | `added.diff`, `pointers-simplicity.txt` |
| Extra lens | whatever its brief names (`claim.txt` always exists after Step 3a) |

`target.diff` exists from Step 2 and `metrics.json` from Step 3. The refuter's `candidates-<n>.md`
is written at Step 7, after aggregation.

| Lens | Runs when | Question | What makes its input different |
|---|---|---|---|
| **Correctness** | always | bugs, logic, edge cases, error paths | diff plus a one-hop impact slice: for each changed exported symbol or signature, its call sites with ±20 lines of context |
| **Conformance** | a corpus matches a concern and S >= 10: one lens per partition of each concern's plan, every partition covered | violations of the team's own standards | only that language's hunks, plus this lens's own grounding slice: its partition's slices of the plan |
| **Tests & behavior** | the diff touches test code (`facts.tests_touched`); a caller handed in a claim; mutation reported survivors; uncovered changed lines were handed in; the PR body, revision summary or commit messages claim a behavior change and S >= 10 | does it do what it claims; what is untested | diff, the test files touching changed files, the claim, and the pointers |
| **Security** | trust boundaries move | injectable or abusable paths | only the trust-boundary hunks plus taint context: where inputs come from and where they land |
| **Architecture** | F >= 5 across >= 2 modules, new public interfaces or services, code moved between layers, or a new dependency pointer | boundaries, coupling, layering, dependency direction | `--stat` shape, the file tree of touched modules, hunks introducing interfaces, the architecture concern's picks |
| **Simplicity** | any duplicate-block pointer; a complexity pointer with after - before >= 5 (a new function counts from 0); more than 3 new comment lines; or 100+ added lines | code this change should delete or reuse | only the added hunks and the simplicity pointers |
| **Extra lens** | the brief's own `trigger`, after its `probe` passes | whatever the brief asks | whatever the brief names |

Security triggers on input parsing, auth, secrets, SQL, shell execution, network calls, or file
path handling.

**The S < 10 fold.** When a corpus matched and S < 10, the Correctness prompt carries the
conformance grounding as variant B (one block per matched concern), and its boundary line becomes
"Style, naming, formatting, test coverage, architecture and security belong to other lenses. Report
defects in behavior, and divergence from the cited standards, each such finding carrying a `bilbo:`
citation." The grounding statement names the fold. Variant B and not a whole read, because a
60K-token read for a five-line diff is what "tiny diffs stay cheap" rules out.

**Extra lenses.** Load `~/.config/ai/review-lenses/*.md`. Run each
brief's `probe`; on failure do not spawn it and
carry its `unavailable` message into the cost line and the report header. Otherwise spawn it when
its `trigger` holds. A missing folder means "extra lenses: none installed".

There is no lens ceiling: every lens runs on its own trigger. A pointer whose lens did not run
because its trigger did not fire (3 or fewer new comment lines and no other signal) is listed in
the header as "flagged, not reviewed".

Spawn rules:

- Print the agent and cost line **before** spawning, naming each lens with the trigger that fired
  it. It is informational, not an approval gate: `review-and-push` and `orchestrate` call this
  skill programmatically and a pause would break them. Example: "Fanning out 5 lenses
  (correctness: always; conformance: go corpus, 2 partitions; tests: test files changed; <name>:
  extra lens) + 1 verifier on claude, lens=opus verify=opus, about 6x a single-pass review; mutation
  up to 10 min before them; then cross-audit by astra (codex) and argon (agy), up to 15 min in
  parallel, plus a refuter pass on what they raise". Count every lens it names and state the time
  boxes, so a reader can multiply by a gate's retries.
- Spawn every lens in **one turn**, the harness's way (Step 1's table): `Agent` with `model: opus` on
  Claude Code; `spawn_agent` with `gpt-6-astra` and high effort on Codex when it takes a model, else
  one `cross-audit spawn --harness codex --workdir <toplevel>` per lens run in parallel from Bash,
  each lens's prompt in a file and its findings in the `-o` file; `invoke_subagent` with model `pro` on agy. Then wait for
  all of them before aggregating.
- Lenses stay **independent**: no lens sees another's output, and there is no cross-lens debate.
  Debate correlates errors; independent reports then aggregated is what buys the coverage.
- Each lens returns **at most 10 findings**. Unbounded finders double false positives for
  marginal extra recall, so the cap is what forces prioritization.
- Every prompt is self-contained. Subagents see nothing of this conversation.
- Web research by a lens or the refuter follows the policy at the end of `references/lens-briefs.md`.

### Step 6 — Aggregate

Run this in the orchestrating session, not another agent, and treat it as a closed list of
operations — freeform synthesis of conflicting findings invents middle grounds that no lens
produced:

1. **Dedup by location** — same file, overlapping lines, same category: merge, keep the clearest
   claim, union the evidence, record `corroboration = N lenses`.
2. **Dedup semantically** — same file, same substantive claim in different words: merge likewise.
3. **Reconcile severity** — on disagreement keep the **higher** and note the split, as
   `major (one lens said minor)`. Never average, never invent a between-tier.
4. **Corroboration ranks, it never gates.** A single-lens finding is a full citizen.
5. **Forbidden here**: rewriting a claim's substance, creating a compromise verdict, adding a
   finding no lens or tripwire produced, or dropping anything. Dropping belongs to the refuter alone.
6. **Tripwires join the pool** from `tripwires.md`, one candidate per file and kind. This is the
   stated exception to item 5's "no lens produced", because the script produced them. Dedup by
   location merges a tripwire with a lens finding.

### Step 7 — Verify

Spawn **one** refuter on the verify model, the harness's way (Step 1); **two** when the merged
pool, tripwire candidates included, exceeds 15 candidates after Step 6 (past that, one refuter's
context holds too many candidates to re-check each against the code), splitting the pool **by
file** so no finding goes to both. Sending
the same finding to two same-family models buys correlation, not signal. The report's agent line
calls these agents verifiers; everywhere else they are the refuter.

The framing is an adversarial kill-mandate, quoted verbatim in `references/lens-briefs.md`:
assume every finding is a false positive, and discard it only against a concrete refutation.
"Seems speculative" is not grounds for discarding — dropping on doubt is the documented way to
lose real bugs.

The refuter works from **fresh evidence**: it re-reads the cited code from disk rather than
trusting the lens's excerpt, and mechanically checks every `bilbo:` citation with
`bilbo cite --plan <plan>` over every plan the lenses read, which confirms the quoted text sits
under the cited heading of a slice someone read. A `quote_elsewhere` or `ambiguous` verdict is
reported as a wrong heading, not a failure.

A failed check downgrades that finding's grounding to `judgment` and is noted; it does not by
itself refute the claim, which stands or falls on the code. The refuter may fetch the web to
refute, labeled `web:`.

It checks `metric:` evidence against `metrics.json` and the cited line. Refuting a tripwire needs a
concrete justification, such as "the deleted test covered `parseLegacy`, which this diff also
deletes". A surviving mutant may be accepted as equivalent with the concrete reason. The refuter
prompt names the throwaway clone or `none`: with a clone it may run a disproving check inside it,
each under `diff-metrics timebox --seconds 120` so nothing it starts outlives the check; with `none`
it reads and searches only. Afterwards restore the clone as `references/mutation.md` says and take
its baseline again; a clone that no longer matches is deleted, and Step 7b runs without one.

Verdicts: `CONFIRMED`, `REFUTED` (with the counter-evidence recorded), or `UNVERIFIABLE`.
`UNVERIFIABLE` findings ship in their own labeled section — they are never dropped.

No AND-gate exists anywhere in this pipeline. A finding never needs two lenses to agree, and
unanimity is a low-signal event rather than a confidence boost.

### Step 7b: Cross-harness audit

Load `references/cross-audit.md` for the bundle, the prompt template, the launch, the parsing and
the landing rules. On `no-audit` or `REVIEW_CROSS_AUDIT=off`, say so in the Audit line and tear
the clone down. Otherwise build the input bundle (this runs with an empty merged pool too: the
auditors may find what the lenses missed) and run
`cross-audit run --harness <Step 1's answer> --bundle ... --prompt-template ... --repo <toplevel>`
(omit `--repo` outside a repository), with `--clone` only when a clone
exists and the target is the user's own code, and `--untrusted` for any other target (`pr N`, `D123`,
another author's branch): then only the Claude auditor, whose sandbox is enforced, runs. Apply the three
landing rules, put missed issues through one refuter pass, then tear the clone down per
`references/mutation.md`.

A `repo_changed` in `integrity.json` invalidates the evidence (Step 8). Every unavailable,
timed-out or discarded auditor, and the codex policy note, is named in the header. None of them
blocks and none counts as clean.

### Step 8 — Report

Write the draft to `<scratchpad>/review/report-draft.md`, then check its citations with every
plan of the run (`--plan` once per plan, from Step 4 and the recall-grounded lenses'
docs-consulted lines):

```bash
bilbo cite --plan <plan> <scratchpad>/review/report-draft.md
```

For a local target, take `diff-metrics fingerprint` again before the Verdict line. A difference, or a
`repo_changed` in `integrity.json`, means the findings describe a tree that no longer exists: print the report, but end it with
`review: evidence invalidated - the repository changed during the review` instead of a Verdict line.

Its `coverage:` and `picked:` lines are what the grounding statement reports as read, word for
word: a source counts as consulted only when bilbo logged its slices as read.

```
## Review: <target> (<N> files, +<a>/-<d>)

Grounding: <concern> from <corpus> (<mode>: picked k of n entries, passed over n-k; read across P partitions / N recall queries) - sources actually read:
<the coverage: and picked: lines of bilbo cite> | dropped candidates: <...> | no coverage for: <...>
Agents: <k> lenses + <m> verifier(s), models lens=<m> verify=<m> (~<k+m>x a single-pass review)
Measured: <checks, with languages> | unmeasured: <check> for <exts or reason> | <mutation status line>
Flagged, not reviewed: <pointer> (<why its lens did not run>) | none
Extra lenses: <name> ran | <name>: unavailable - <message> | none installed
Audit: <auditor> ran (disputed d, contested c, missed m, confirmed k) | <auditor>: unavailable (<reason>) | skipped (no-audit)

### Confirmed findings
1. [MAJOR] path/file.go:42 — <claim>
   evidence: `<code quote>` - grounding: bilbo:<id>#Errors "<quote>" - corroboration: 2 lenses
   refuter: confirmed — <one line why>
   audit: disputed by <auditor> - <evidence>            (only when an auditor disputes it)
...

### Unverified (could not be confirmed or refuted — read skeptically)
...

### Refuted during verification (not actionable; kept for transparency)
- <claim> — refuted: <concrete counter-evidence, one line>

### Checked and clean
<one or two lines per lens on what was examined and found fine>

Verdict: N confirmed (a critical / b major / c minor / d nit), M unverified, R refuted.
```

- The **grounding statement is mandatory**, including when it reads "ungrounded - no corpus
  covers this". Having sources on disk never proves they were consulted, so the review states
  what it picked and read.
- The **measured/unmeasured line and the Audit line are mandatory**, like the grounding statement.
  A contested refutation sits under Unverified with both evidences; an audit-confirmed finding
  carries `source: audit (<auditor>)`.
- The **Verdict line is a stable contract**: `review-and-push` and `orchestrate` key off it.
- No fixes are applied. Fixing is follow-up work outside this skill.

## Failure modes

| Situation | Action |
|---|---|
| No spawning tool for this harness | Print `review: cannot run here - no tool to spawn lenses`; no Verdict line |
| The repository changed during the review | Keep the report; end with the `evidence invalidated` line instead of a Verdict line |
| No corpus found for any concern, by name or through `bilbo recall --library` | Proceed ungrounded; label it in the grounding statement |
| `gh` or `arc` missing or unauthenticated for a remote target | Report exactly what failed and stop; never substitute a local diff |
| Empty diff | Say so and stop |
| No concern matches | Ungrounded review, labeled as such; never fabricate coverage |
| A lens errors or returns nothing | Continue with the rest; note the gap in the report |
| Merged pool empty | Skip the refuter, not Step 7b; clean report with the grounding statement and the per-lens "checked and clean" lines |
| A `bilbo:` citation fails the refuter's check | Downgrade its grounding to `judgment` and note it; the claim stands or falls with the refuter |
| `diff-metrics`, lizard, scc or Python missing; a stale handed-in file; mutation, extra-lens or audit trouble | The table at the end of `references/metrics.md`; nothing is ever reported clean |

## Hard prohibitions

Never:

- Edit repository files, commit, push, or post anywhere. Writes go to the scratchpad only.
- Fabricate a citation - no source nobody picked, no heading nobody read.
- Drop a finding without a stated, concrete refutation.
- Require lens agreement, or treat unanimity as confirmation.
- Rewrite a claim or invent a compromise severity during aggregation.
- Hardcode the corpus list or the default branch. Discover both at runtime.
- Omit the grounding statement, least of all when the review ran ungrounded.
- Answer a standards question from model memory when no source came up.
- Treat an unmeasured check as clean, or an audit that did not run as a clean audit.
- Run the project's code anywhere but the throwaway clone, or for a target that is not the user's own code.
- Report a clean review when no lens ran.
- Edit or hand-write `metrics.json` or a bundle file `diff-metrics` writes.
- Use or name a Fable model.
