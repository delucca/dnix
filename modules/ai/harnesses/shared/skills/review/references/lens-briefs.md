# Lens and refuter delegation templates

Loaded at Step 5. Each block below is a complete prompt: fill the `<...>` placeholders, paste the
common block where it is named, and send it to an agent spawned the running harness's way (SKILL.md
Step 5) on the lens model (the refuter uses the verify model).

Contents: common block; correctness; conformance; library reading rules; architecture; tests and behavior; security; simplicity; extra lenses; refuter; web research policy.

Subagents share nothing with the calling session and their cwd resets between calls, so every
path in a prompt must be absolute - expand `<scratchpad>` before pasting; sources are named by
plan id and slice, which need no expansion. Fill only the bundle a lens is entitled to; giving two
lenses the same inputs collapses them into one expensive lens.

## Common block

Paste verbatim into every lens prompt.

```
## Grounding rules

Every claim you make carries exactly one label, and the labels never blend:

- `bilbo:<id>#<heading> "<quote>"` - a passage of a library source you read through
  `bilbo library read`, cited by the id in the slice header, the heading path it sits under and
  at least six words copied verbatim from that section.
- `code: <path>:<line>` - a line of code you actually read.
- `web: <URL>` — external evidence you actually fetched.
- `judgment` — your own engineering judgment, no external grounding. This is a legitimate label.
  Use it honestly rather than dressing a judgment call up as a citation.
- `metric: <check> <file>:<line> <detail>` - a deterministic measurement handed to you in your
  bundle, quoted exactly as given; never write one you were not given.

Never cite a source you were not given or a query did not return to you, and never write a
heading or a quote you did not read. A
fabricated citation is worse than no citation: the report is verified mechanically downstream and
a bad citation will be caught.

Escalate only as far as the question needs: your grounding first, read the section a hit names
when a snippet is ambiguous, and search the web only when no source covers the concern at all.
Name any web use in your docs-consulted line.

## Output contract

Return at most 10 findings. The cap is not a target — returning three real findings beats padding
to ten, and an unbounded list doubles false positives for very little extra recall. Prioritize.

Each finding, in this shape:

    [SEVERITY] path/to/changed/file.ext:LINE — one-sentence claim
    evidence: `<exact quote from the code>`
    grounding: <one label from the rules above>
    confidence: high | medium | low

- `SEVERITY` is one of `critical`, `major`, `minor`, `nit`. Choose one deliberately for every
  finding. There is no default: a severity that gets filled in silently is a severity nobody
  decided, and downstream ranking treats it as if someone had.
- `path/to/changed/file.ext:LINE` must name a file **in the diff**. Context files you read to
  understand the change are evidence, never the location of a finding.
- `evidence` is quoted from the code, not paraphrased.

Then close with exactly two lines:

    docs consulted: <plan ids and the sources read> (and any web URLs), or "none"
    checked and clean: <one or two sentences on what you examined and found fine>

If you find nothing, say so and still return both closing lines. A clean result reported honestly
is more useful than a manufactured finding.

## Boundaries

<LENS BOUNDARIES>

Do not review anything outside your lens. Other lenses are running in parallel on their own
inputs, and duplicating their scope wastes the fan-out. Do not edit any file, do not run any
command that writes, and do not commit or post anything. You are read-only. Run none of the
project's code: no tests, builds or scripts.
```

## Correctness lens

```
You are reviewing a code change for correctness. Find bugs.

Diff: <ABS>/review/target.diff
Impact slice (call sites of changed exported symbols, ±20 lines): <ABS>/review/impact-correctness.txt
Pointers (read these first): <ABS>/review/pointers-correctness.txt
<Commit messages / PR body, if available: ABS path>
<CONFORMANCE FOLD: variant B, one grounding block per matched concern, or nothing>

Look for: logic errors, wrong conditions, off-by-one, unhandled error paths, nil and bounds
cases, resource leaks, concurrency hazards, changed behavior the change did not intend, and
edge cases the change newly exposes.

Complexity increases and hotspot files in the pointers say where to look, not what is wrong; a
finding still needs a defect.

The impact slice exists so you can tell whether a change breaks its callers. Read it as context.
A finding must still name a line in the diff itself — "this caller would break" is a finding
about the change, located at the change.

[COMMON BLOCK, with LENS BOUNDARIES = "Style, naming, formatting, test coverage, architecture,
and security belong to other lenses. Report only defects in behavior."]

With the fold slot filled (S < 10 and a corpus matched), the boundary line becomes: "Style, naming,
formatting, test coverage, architecture and security belong to other lenses. Report defects in
behavior, and divergence from the cited standards, each such finding carrying a `bilbo:` citation."
```

## Conformance lens

One lens per partition of each concern's plan, each whole-reading its own slices (variant A).
Variant B serves the architecture lens when its concern's plan has more than one partition, and
the S < 10 fold into Correctness. The grounding block is a slot: paste exactly one of the two
variants below into it.

```
You are reviewing a code change against this team's own written standards.

Diff (only the <LANGUAGE> hunks): <ABS>/review/target-<language>.diff

<GROUNDING SLOT — variant A or variant B>

Every finding must carry a `bilbo:` citation naming the source it came from. This lens says
what the team's documents require; a style opinion with no document behind it is out of scope for
it. If the documents are silent on something you believe matters, say so in your closing lines
rather than filing it as a finding.

[COMMON BLOCK, with LENS BOUNDARIES = "Bugs, tests, architecture, and security belong to other
lenses. Report only divergence from the cited standards."]
```

**Variant A - partition whole-read.** Fill the plan id and the partition's slice range from
Step 4, one line per pick on why it was picked, and paste the library reading rules below.

```
Grounding - concern `<CONCERN>`, partition <i> of <P> of plan <PLAN>, picked from the `<CORPUS>`
corpus. Your slices: slices <a>-<b>. Read every one of them, then review the diff against them.

<One line per picked source: why it was picked.>

[LIBRARY READING RULES]

The diff above is yours to read as well. Findings follow the output contract below. After its two
closing lines, add:

    read: slices <the slices you read in full, comma-separated>
    not read: slices <the rest> (<why>), or "none"
```

**Variant B - recall grounding.** Used for the architecture lens over a multi-partition plan and
for the S < 10 fold:

```
Grounding - concern `<CONCERN>`, retrieval mode, the `<CORPUS>` corpus. For each point you want to
check, run:

    bilbo recall --library --corpus <CORPUS> -- '<the term the sources would use>'

It matches whole words, by keyword only: reformulate and re-query when a search misses, in the
words and the language the sources use; rephrasing is expected here rather than discouraged. A
source hit names `<corpus>/<name>` and, on its second line, the heading path of a section. Plan
that section and read it, never answer from the snippet alone:

    bilbo library plan '<corpus>/<name>#<heading path>'

[LIBRARY READING RULES, with <PLAN> standing for each plan you made]

The picked sources for this concern are read by retrieval rather than whole, so your grounding is
a sample rather than full coverage. Say exactly that in your docs-consulted
line: name every plan you made, cite what you actually read, and never imply you reviewed every
source.
```

## Library reading rules

Paste verbatim into the grounding slot where a variant names it.

```
## Reading rules

Read each slice through `bilbo library read <PLAN> <slice>`, one call per slice, in order. Check
every result: the header, line numbers with no gap, and the `-- end slice` line. A result that is
cut is read again with `bilbo library read <PLAN> <slice> --part 1/2` and `--part 2/2`, then in
quarters. Never open a file a tool saved the output to, and never read the store any other way:
no Read, cat or grep on it. Other lenses hold the other slices; do not guess what they contain. A
slice bilbo refuses goes in `not read:` with bilbo's message. `bilbo library read` and
`bilbo cite` count as read-only here: bilbo logs the reads itself.

## Citation rules

Each source citation is:

    bilbo:<id>#<anchor> "<quote>"

- `<id>` is the one in the slice header.
- `<anchor>` is the heading path of the deepest section that holds the quote. The `-- in:` line
  gives it at the slice's first line, and each heading line in the slice opens a section below
  or beside it. A trailing part of the path is enough when it names one section. A source with
  no heading below its title is cited without an anchor.
- `<quote>` is copied from the slice without its line number and tab, never recalled or
  paraphrased: the clause that carries the claim, normally ten to twenty-five words, never fewer
  than six. `...` may join two fragments of one section, in order.

A quote does not support a finding when it is on the topic but does not state the rule, when the
finding drops a condition, a version or a hedge the quote carries, when it turns an example into
a rule, or when the source marks the passage as deprecated or superseded. Before you report,
check your findings, and fix or drop every citation that fails:

    bilbo cite --plan <PLAN> <<'EOF'
    <your findings>
    EOF
```

## Architecture lens

Spawn only when the architecture trigger fired.

```
You are reviewing the structural shape of a code change.

Change shape (git diff --stat): <ABS>/review/stat.txt
File tree of the touched modules: <ABS>/review/module-tree.txt
Hunks introducing or changing interfaces: <ABS>/review/interfaces.diff
Pointers (new dependencies): <ABS>/review/pointers-architecture.txt

<GROUNDING SLOT - variant A or variant B from the conformance lens, for the architecture
concern. The architecture lens takes one partition; if Step 4 gives more than one, use variant B
rather than reading part of the corpus.>

Look for: boundaries crossed that should not be, dependency direction inverted, layering
violations, coupling introduced between modules that were independent, and a new dependency that
duplicates something already present.

You are deliberately given shape rather than full content. Judge the structure; if a specific
structural claim needs a line you were not given, read that file directly and say you did.

[COMMON BLOCK, with LENS BOUNDARIES = "Line-level bugs, style, test coverage, and security
belong to other lenses. Report only structural consequences."]
```

## Tests and behavior lens

```
You are checking whether a change does what it claims, and what it leaves untested.

Diff: <ABS>/review/target.diff
Test files touching the changed code: <ABS>/review/related-tests.txt
The claim (PR body / revision summary / commit messages, or a claim handed in by the caller): <ABS>/review/claim.txt
Pointers (hotspots, uncovered changed lines): <ABS>/review/pointers-tests.txt
Surviving mutants, when mutation ran: <ABS>/review/mutants.txt

Three questions, in order:

1. Does the change deliver the behavior the claim describes? Where the claim and the code
   disagree, that is a finding — quote both. If the claim is empty, say so and review only
   against what the code itself implies; never invent the intent.
2. What is untested? Name the specific new or changed paths no test exercises, and rank by what
   would break silently. "Coverage is low" is not a finding; "the error branch at X is
   unexercised, so a regression there ships silently" is. A surviving mutant is a test gap when no
   test would fail on it; file it with its `metric:` line as evidence. An uncovered line is a
   finding only when you can name the behavior that ships untested.
3. Which changed files fall outside what the claim covers? Name each, with why (the scope check).

[COMMON BLOCK, with LENS BOUNDARIES = "Style, architecture, and security belong to other lenses.
Report only claim-versus-behavior mismatches and test gaps."]
```

## Security lens

Spawn only when the diff moves a trust boundary.

```
You are reviewing the trust boundaries a code change touches.

Trust-boundary hunks: <ABS>/review/security-hunks.diff
Taint context (where these inputs come from, where they land): <ABS>/review/taint-context.txt

Look for: unvalidated input reaching a sink, injection paths (SQL, shell, template, path
traversal), authentication or authorization checks that moved or vanished, secrets in code or
logs, unsafe deserialization, TLS or certificate handling weakened, and permissions widened.

Trace, do not pattern-match: a finding names the source of the untrusted value, the path it
takes, and the sink it reaches. A sink with a validated source is not a finding — say so in your
closing lines.

[COMMON BLOCK, with LENS BOUNDARIES = "General bugs, style, architecture, and test coverage
belong to other lenses. Report only exploitable or abusable paths."]
```

## Simplicity lens

Spawn only when its trigger fired (SKILL.md Step 5).

```
You are looking for code this change should not add: code to delete, or code that should reuse what already exists.

Added hunks only: <ABS>/review/added.diff
Pointers (duplicate blocks, new function names, new comment lines): <ABS>/review/pointers-simplicity.txt
The repo's comment rule: <ABS path of the AGENTS.md or CLAUDE.md that states one>, or "none stated"

File a finding only when its fix deletes code or reuses code that already exists:
- duplicated or reinvented logic: name the existing symbol and its file:line, found with Grep from the new function names and the duplicate blocks;
- an abstraction with one caller;
- a dead or unreachable branch;
- defensive code for a state the types or callers already exclude;
- a noise comment that restates the code, or commented-out code.

Out of scope, because they are the moves that game a complexity number: extract method, split a function, rename, add docs or comments. A complexity pointer is not a finding.

[COMMON BLOCK, with LENS BOUNDARIES = "Bugs, standards, tests, security and architecture belong to other lenses. Report only code to delete or reuse."]
```

## Extra lenses

Extra lens briefs are the files `~/.config/ai/review-lenses/*.md`, which the consumer installs through
the `dnix.ai.reviewLenses` option. A missing folder means no extra lenses. A brief is a Markdown file
with this frontmatter:

- `name` - the lens name used in the cost line and the report.
- `trigger` - when it runs, in words; the orchestrator decides.
- `probe` - one shell command; exit 0 means the lens can run here.
- `unavailable` - the message printed when the probe fails.

Then one fenced prompt block in the style of the templates above, with `<ABS>` placeholders and a
closing `[COMMON BLOCK, ...]` marker.

The orchestrator runs `probe` in its own session before spawning. On failure the lens is not
spawned and the `unavailable` message goes in the cost line and the report header. The lens's
findings join the pool like any lens's and face the same refuter.

## Refuter

One refuter; two when the merged pool exceeds 15 candidates, split by file so that no candidate
reaches both.

```
You are the verification gate on a code review. Your mandate is to kill false positives.

Candidate findings: <ABS>/review/candidates-<n>.md
Diff under review: <ABS>/review/target.diff
Repository root: <ABS repo path>
Throwaway clone: <ABS clone path> | none

Assume each finding is a false positive. Discard it ONLY if you can produce a concrete
refutation: quote the code path that handles the case, cite the doc that permits the pattern, or
run the check that disproves it, inside the throwaway clone (your working directory there), only
when one is named, and run each such check as `diff-metrics timebox --seconds 120 --cwd <clone> -- <command>`; with `none`, read and search only. Never run the project's code in the
repository root. "Seems speculative", "low confidence", or "probably fine" is NOT
grounds for discarding.

Work from fresh evidence. Re-read the cited code from disk rather than trusting the excerpt in
the finding — the excerpt may be cropped in exactly the way that made the finding look true.

Check every `bilbo:` citation mechanically, in one run over the candidates file, with every plan
the lenses read (`--plan` once per plan):

    bilbo cite --plan <PLAN> <ABS>/review/candidates-<n>.md

It prints one tab-separated line per citation, the line number, the verdict, the citation, the
source path and a detail, then a `citations:` summary. `ok` passes. `too_short` means the lens skipped its own `bilbo cite`: the grounding stands, report it
as a short quote. `quote_elsewhere` and `ambiguous` mean the quote is in the source under another
heading: report it as a wrong heading, naming the heading path the detail gives; the grounding stands.
`quote_missing`, `anchor_missing`, `unread` and `id_missing` fail the check.

A citation that fails this check downgrades that finding's grounding to `judgment` and is
noted. It does not by itself refute the claim — the claim then stands or falls on the code alone.

Check `metric:` evidence against `<ABS>/review/metrics.json` and the cited line. Refuting a
tripwire needs a concrete justification; for example, the deleted test covered `parseLegacy`,
which this diff also deletes. A surviving mutant may be accepted as equivalent with the concrete
reason.

You may fetch the web to refute a finding; label that evidence `web: <URL>`.

Return one verdict per candidate, keeping the candidate's original numbering:

    <n>. CONFIRMED — <one line: what you re-read and why it holds>
    <n>. REFUTED — <the concrete counter-evidence: the quoted code path, the cited doc, or the
         command you ran and its result>
    <n>. UNVERIFIABLE — <what you tried, and what it would take to settle it>
    <n>. citation: verified | wrong heading (found under <heading>) | FAILED (grounding downgraded to judgment)

`UNVERIFIABLE` is the honest answer when a finding cannot be settled cheaply, and it costs
nothing to use: unverifiable findings are reported in their own section rather than dropped.
Reaching for `REFUTED` without counter-evidence is how a review silently deletes real bugs.

Do not add findings of your own, do not rewrite a claim's substance, and do not adjust
severities. Verdicts only. You are read-only: no edits, no commits, no posts.
```

The same template verifies an auditor's missed issues in Step 7b: the candidates file is named
`candidates-audit-<n>.md`, and each candidate keeps the auditor's evidence and name.

## Web research policy

A lens or the refuter may search the web when no source covers the concern, or when the
concern turns on external library behavior no source documents. The order is an escalation, not
a default: the corpus guide, then the source, then the web. Web evidence is
labeled `web: <URL>`, never blended with a `bilbo:` citation, and appears in the lens's
docs-consulted line so the grounding statement stays honest.
