# Section menu

Pick sections from this menu based on what the project actually needs — never fill a
template. Every section you add is surface area that can rot; every section you skip must
be a deliberate call, not an oversight.

## Tier 1 — mandatory (every README)

| Section | What it must do |
|---|---|
| Title | H1, matching the repo/package name. If the display name differs: `# Display Name _(package-name)_` |
| Description | 1–3 sentences: what it does and why you'd use it. What/why only — no tech stack here |
| Installation | Copy-pasteable command(s). Prerequisites (runtime, minimum versions, OS) listed first |
| Usage | Minimal runnable example with expected output. CLI tools: real command + real output |
| License | SPDX identifier, link to the LICENSE file, last section. Restrictive license: flag it near the top instead |

## Tier 2 — recommended (most projects)

- **Features / highlights** — short bulleted list of key capabilities, right after the description.
- **Contributing** — whether contributions are welcome; link CONTRIBUTING.md if it exists.
- **Table of contents** — when the README exceeds ~100 lines.
- **Support / getting help** — issue tracker, chat, forum, or "none".
- **Maintainers / credits** — who to contact; funding or inspiration acknowledgments.

## Tier 3 — situational (only when applicable)

- **Badges** — 2–4 meaningful ones (build, version, license). Never a wall; each badge must answer "what does the typical reader gain from this?"
- **Screenshots / GIFs** — high value for anything visual (UI, CLI output, plots). Inline essential images; they must show the current version.
- **API reference** — inline only for small libraries (roughly <10 exports); otherwise link to generated or dedicated docs.
- **Configuration** — flags, env vars, config files. Required for apps/services and most CLIs.
- **Background / motivation** — when the purpose or domain isn't obvious.
- **Roadmap** — only if a public plan genuinely exists.
- **Security** — vulnerability reporting channel, if one exists.
- **Built with** — never leading; the purpose comes before the stack.
- **Project status** — top of the file when development has stalled or the project is experimental.
- **Citation** — research/academic projects (CITATION.cff or BibTeX).
- **Changelog** — always a link to CHANGELOG.md or releases, never inlined.

## Default order

Title → badges → description → features → ToC → Installation → Usage → API/Configuration
→ Contributing → License.

The cognitive funnel is enforced at the document level: what/why always precedes any how,
and each section lets the reader bail out or go deeper. One documented exception: for a
small library whose code snippet is the strongest qualifier, Usage may precede
Installation (Art of README's order).

## Per-artifact-type deltas

| Section | OSS library | CLI tool | App / service | Internal repo | Data / research |
|---|:-:|:-:|:-:|:-:|:-:|
| Install (package manager) | Required | Required | Required | Required | — |
| Usage code block | Required | Required (commands + output) | Required (setup + run) | Required | — |
| API reference | If small | — | — | — | — |
| Configuration | If needed | Required | Required | Required | — |
| Deployment | — | — | Required | Situational | — |
| Dev setup | Recommended | Recommended | Required | Required | — |
| Motivation / background | Situational | Situational | Recommended | Situational | Required |
| Method and results | — | — | — | — | Required |
| Data dictionary | — | — | — | — | Required |
| Citation | Situational | — | — | — | Required |
| License | Required | Required | Required | Team policy | Required |
| Contributing | Required | Recommended | Recommended | Team policy | — |

Internal repos: drop license/contributing boilerplate in favor of team conventions; add
ownership and dev setup instead.

Data/research repos use a different skeleton entirely (Cornell/Tilburg): general info
(title, authors/PI, dates, funding) → motivation → data and file overview → methodology →
data dictionary (variables, units, missing-data codes) → sharing/access/citation →
running instructions.

## Where sources disagree — and the default this skill takes

| Question | Default | Rationale |
|---|---|---|
| Install before Usage? | Yes (chronological) | Matches standard-readme and every major template; Usage-first allowed for small libraries (funnel exception above) |
| How many badges? | 2–4 meaningful | Art of README's "judicious" beats template badge walls |
| API docs inline? | Only <~10 exports | Larger APIs belong in dedicated docs (banesullivan) |
| Changelog in README? | Never — link | Inline history grows without bound |
| License placement | Last | standard-readme; restrictive licenses surface at the top instead (Art of README) |
