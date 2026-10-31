# Review checklist

## Requirement levels and grading

Checklist levels map directly to review finding ranks:

| Level | Meaning | Review rank |
|---|---|---|
| MUST | Consensus-mandatory; absence misleads or blocks readers | **Blocking** |
| SHOULD | Strong best practice; absence degrades the README | **Important** |
| MAY | Valuable in context; absence is a suggestion, not a defect | **Advisory** |

## The checklist

### Identity
- [ ] MUST — project name is the first H1
- [ ] MUST — title matches the repository and manifest names (or shows both)
- [ ] SHOULD — project URL linked from or near the title
- [ ] MAY — author/owner identified; banner or logo

### Description
- [ ] MUST — short what/why description present before any detail
- [ ] SHOULD — under ~120 characters for the one-liner; expands in 1–2 paragraphs at most
- [ ] SHOULD — describes what the project does, not what it's built with
- [ ] SHOULD — matches the manifest's description field
- [ ] MAY — background/motivation section for non-obvious domains

### Installation
- [ ] MUST — install section with a copy-pasteable code block
- [ ] SHOULD — prerequisites (runtime, tools, minimum versions) listed before the command
- [ ] SHOULD — command matches the manifest package name (verified, not assumed)
- [ ] SHOULD — platform variants where they genuinely differ

### Usage
- [ ] MUST — usage section with a minimal working code block
- [ ] SHOULD — CLI invocation with real output shown, if a CLI exists
- [ ] SHOULD — example imports and symbols exist in the source (verified)
- [ ] MAY — example code kept as a runnable file in the repo; screenshots for visual projects

### Navigation
- [ ] MUST — ToC when the README exceeds ~100 lines, with working anchors
- [ ] SHOULD — descriptive sentence-case headings; separate concerns in separate sections
- [ ] SHOULD — deeper docs linked and briefly described, not just listed

### Community
- [ ] MUST — contributing stance stated (or linked) for public projects
- [ ] MAY — support channel; maintainers/credits; code of conduct link

### Legal
- [ ] MUST — license stated and consistent with the LICENSE file
- [ ] SHOULD — SPDX identifier; last section (restrictive licenses flagged early instead)

### Integrity (verify with tools, never judgment)
- [ ] MUST — no broken links: relative paths exist, anchors match headings, external URLs return 2xx/3xx
- [ ] SHOULD — no stale hardcoded versions; badges load and point at this repo
- [ ] SHOULD — code blocks would pass the project's own linter

### Structure
- [ ] SHOULD — cognitive-funnel order: what/why before any how; each section a valid bail-out point
- [ ] SHOULD — under ~300 lines; longer content extracted to linked docs
- [ ] SHOULD — nothing inlined that has a dedicated home (changelog, full API docs, contributing guide)

## Review output format

```markdown
## README review — <repo>

### Blocking
- **<finding>**: <where> — <why it matters>. Fix: <concrete action>.

### Important
- ...

### Advisory
- ...

### Verified OK
- <check that passed, with how it was verified>
```

Order findings most-severe first within each rank. Every finding names a concrete fix.
An empty Blocking section is a legitimate result — never manufacture findings.

## Mechanical checks in detail

| Check | Procedure |
|---|---|
| Relative links | For each `](path)`: Glob the path from the README's directory; missing file → Blocking |
| Anchors | For each `](#anchor)`: a heading must slugify to it (lowercase, spaces→dashes, punctuation dropped) |
| External links | `curl -sIL -o /dev/null -w "%{http_code}" <url>` per unique URL; 4xx/5xx → Blocking; offline → report "not checked" |
| Install command | Extract the package name from install code blocks; compare to the manifest name field |
| Title match | First H1 vs repo directory name and manifest name; mismatch without a stated alias → Important |
| Description match | README one-liner vs manifest description field; drift → Important |
| Example symbols | Grep each imported/called symbol from usage blocks in the source tree; missing → Blocking |
| Badge targets | Badge URLs must reference this repo/pipeline; foreign or dead badges → Important |
| Length / ToC | Line count >100 without a ToC → Important |
