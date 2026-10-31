# Style and anti-patterns

## Writing rules

1. **Open with what + why.** The first substantive text after the title answers "what does
   this do?" and "why would someone use it?" in two to four plain sentences.
2. **Show, then tell.** A minimal runnable example appears before any API detail or deep
   explanation.
3. **Second person, active voice, present tense.** "Edit the config file", not "the
   configuration file should be edited". Describe what the software does, not what it will do.
4. **Plain language.** Define jargon on first use. No idioms or cultural references (they
   defeat non-native readers and translation). No marketing superlatives — facts or
   benchmarks.
5. **Contractions are fine; memes are not.** Tone: a knowledgeable colleague explaining the
   project in a hallway — warm, efficient, specific.
6. **Sentence-case headings.** Capitalize only the first word and proper nouns. Title Case
   Reads Like Marketing.
7. **Front-load everything.** The first sentence of each section and paragraph carries the
   key point. Conditions before instructions ("Before running X, install Y").
8. **Every code block is copy-pasteable from a clean state.** No hidden imports, undefined
   variables, or state assumed from a previous block.
9. **Pick the right shape.** Prose for what/why; numbered lists for steps; bullets for
   features and prerequisites; code blocks for anything the reader types.
10. **Brevity is a maintenance strategy.** A section beyond ~40 lines probably belongs in a
    linked doc; a README beyond ~300 lines definitely hides one. Less surface, less rot.

## Anti-pattern catalog

| Anti-pattern | Detector signal | Remedy |
|---|---|---|
| Missing what/why | First 25 lines have no plain-language description | Add a 2–4 sentence what/why as the first content |
| Buried lede | Logo, badges, or ToC before the name and one-liner | Name + one-liner first; decoration after |
| Wall of badges | More than ~4 badge images before the description | Keep 2–4 that serve the reader; drop the rest |
| Curse of knowledge | Unexpanded acronyms, undefined domain terms | Define on first use or link a definition |
| Missing prerequisites | Install section jumps straight to the command | List runtime, tools, and minimum versions first |
| No usage example | No code block in the first two screenfuls | Add a minimal runnable example |
| Non-runnable examples | Imports or variables not defined in the block | Make each block self-contained |
| README as changelog | Version history inlined | Link CHANGELOG.md or releases |
| Over-long README | >~300 lines | Extract sections into linked docs |
| Marketing fluff | Superlatives without evidence | Replace with facts or benchmarks |
| Dead links | URLs that 404, files that don't exist | Fix, remove, or inline the essential content |
| Stale screenshots | Images showing an old UI or output | Update or remove |
| Generic boilerplate | Sentences that could describe any project | Rewrite with project-specific specifics |
| Passive-voice instructions | "should be configured", "can be run" | Active voice, address the reader |
| FAQ as junk drawer | FAQ section accumulating misc content | Fold answers into the proper sections |
| Missing license | No license section or LICENSE file | Add both; state the SPDX identifier |

## Rot signals (edit and review modes)

Incorrect documentation is worse than missing documentation. Flag:

- Version numbers in examples that don't match the latest release or manifest.
- Function names or signatures in examples that differ from the source.
- Screenshots showing UI or output that no longer matches reality.
- Links that 404; badges pointing at another repo or a dead pipeline.
- "Coming soon" sections older than the last few releases.
- Install steps referencing deprecated package managers or renamed packages.

Prefer version-agnostic writing: `latest` doc URLs, un-pinned install commands where the
latest version is the common case, behavior descriptions over implementation descriptions.
