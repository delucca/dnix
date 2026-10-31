# Digest rules — the research behind /tldr

Distilled from human-communication frameworks (BLUF, Smart Brevity, Minto Pyramid,
plain-language guidelines, inverted pyramid, NN/g scannability research) and
LLM-output-control guidance. SKILL.md encodes the core rules; this file holds the
full set and the numbers, for when a judgment call needs backing.

## The rule set

1. Open with the single most important sentence — the conclusion, result, or required
   action, never context. (BLUF / Army AR 25-50; Minto; inverted pyramid)
2. The first sentence must survive alone: a reader who stops there still knows the
   outcome. (Inverted pyramid "cut from the bottom" test)
3. Order everything after the lede by strictly diminishing importance, so the digest
   can be truncated anywhere and still work. (Inverted pyramid)
4. Group supporting detail under 2-4 non-overlapping points. (Minto Pyramid, MECE)
5. One idea per sentence; one topic per paragraph. (Plain language)
6. Keep sentences under 20 words, averaging ~15. (Plain language; Army standard)
7. Active voice with a named actor: "the migration broke auth", not "auth was
   impacted". (Plain language; AR 25-50)
8. Front-load keywords: the first two words of every bullet must carry the
   information — scanners often read only those. (NN/g F-pattern)
9. Bullets only for parallel, enumerable facts; keep causal reasoning in prose.
   Bullet walls destroy the connective tissue of an argument. (NN/g; Smart Brevity
   critiques)
10. Bold only load-bearing words or numbers, never whole sentences. (Smart Brevity;
    NN/g)
11. Offer depth as an explicit pointer ("ask to expand X") instead of inlining it.
    (Smart Brevity "Go deeper")

## The numbers

| Target | Value | Source |
|--------|-------|--------|
| Headline | ≤ 6 words of payload, strongest words first | Axios Smart Brevity |
| Body sentences | < 20 words, average ~15 | Plain-language guidelines; Army writing standard |
| Paragraphs | ≤ 2 sentences on screens | Plain language; Smart Brevity |
| How much users actually read | ~20-28% of words on a page; 79% scan | NN/g |
| Smart Brevity effect | ~40% shorter with the same information | Axios HQ |

## Reconciling the frameworks

- Smart Brevity's ~6-word aspiration vs plain language's 15-20-word sentences:
  6 words is for the headline payload, 15-20 for body sentences.
- Smart Brevity bullets everything; NN/g says bullet walls kill reasoning:
  bullets for enumerable facts, prose for causal chains.
- Inverted pyramid is a linear importance decay; Minto is a grouped tree:
  for agent-reply digests use BLUF + at most one level of grouping, importance
  decay within it.

## LLM-side techniques

From Anthropic's prompting documentation and LLM-verbosity research:

1. State the positive format target, never the prohibition: "respond in flowing
   prose" beats "don't use markdown". (Anthropic best practices)
2. Give a concrete output template, not an adjective like "concise". The digest
   skeleton in SKILL.md Step 3 is that template. (Anthropic best practices)
3. Anthropic's tested session wording, used verbatim in Step 5: "Keep responses
   focused, brief, and concise. Keep disclaimers and caveats short, and spend most
   of the response on the main answer. When asked to explain something, give a
   high-level summary unless an in-depth explanation is specifically requested."
   (Opus 5 prompting guide)
4. Answer-first ordering: the first sentence answers "what happened / what did you
   find". (Opus 5 prompting guide)
5. Budget in structural units (max 5 body lines), because models cannot count words:
   GPT-4-class models overshoot word targets ~50% of the time above 200 words
   (arXiv 2406.17744). The word budget in Step 4 survives ONLY because `wc -w` is an
   external check, not self-counting.
6. Name each padding behavior with its replacement: no restating the request, no
   politeness openers/closers, no unsolicited caveats, no summary-of-the-summary —
   the three verbosity failure modes YapBench measures (arXiv 2601.00624).
7. Motivate the rule: the output is scanned by an engineer mid-task; motivated rules
   outperform bare rules. (Anthropic "be clear and direct")
8. One before→after example steers format more reliably than any rule. (Anthropic)
9. Escape valve: an explicit user request for depth always beats the budget.
10. Why models pad at all: RLHF reward models score longer answers higher (length
    bias, arXiv 2310.10076, 2511.12573); newer frontier models are more verbose than
    2023-era ones (YapBench). Brevity therefore needs standing counter-pressure in
    context — a one-off "be concise" decays (inference, flagged).

Anti-patterns, verified against sources: bare "be concise" with no format spec;
negative-only ban lists; self-counted word budgets; "don't think" instructions
(cause reasoning-tag leakage per Anthropic); relying on output styles (deprecated
Nov 2025) or effort settings (they do not shorten visible responses).

## Sources — human frameworks

- BLUF — https://en.wikipedia.org/wiki/BLUF_(communication)
- BLUF / AR 25-50 mechanics (secondary summaries; the ~15-word figure comes from
  these, not the regulation text) — https://writemymcoer.com/army-writing-style-guide
  and https://netsuite.blog/army-writing-regulation-ar-25-50-guide
- Smart Brevity — https://www.axioshq.com/smart-brevity and
  https://help.axioshq.com/hc/en-us/articles/40406826943891-Understanding-Smart-Brevity
- Smart Brevity critique (6-word headline axiom, limits of bulleting) —
  https://newrepublic.com/article/167733/axios-guide-writing-well-neither-smart-brief-smart-brevity-book-review
- Minto Pyramid Principle — https://strategycase.com/the-pyramid-principle-case-interview/
- Minto / MECE (Barbara Minto interview) —
  https://www.mckinsey.com/alumni/news-and-events/global-news/alumni-news/barbara-minto-mece-i-invented-it-so-i-get-to-say-how-to-pronounce-it
- Plain language numeric targets —
  https://governor.wa.gov/issues/efficient-government/plain-language/plain-language-guidelines
  and https://digital.gov/guides/plain-language
- Inverted pyramid —
  https://owl.purdue.edu/owl/subject_specific_writing/journalism_and_journalistic_writing/the_inverted_pyramid.html
  and https://en.wikipedia.org/wiki/Inverted_pyramid_(journalism)
- NN/g F-pattern — https://www.nngroup.com/articles/f-shaped-pattern-reading-web-content/
- NN/g reading share (20-28%) — https://www.nngroup.com/articles/how-little-do-users-read/
- NN/g scan vs read (79%/16%) — https://www.nngroup.com/articles/how-users-read-on-the-web/

## Sources — LLM output control

- Anthropic prompting best practices (positive format targets, output templates,
  examples as format steer, avoid-excessive-markdown block) —
  https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
- Anthropic Opus 5 prompting guide (tested conciseness wording, answer-first
  narration, end-of-prompt tone echo, effort settings don't shorten output) —
  https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5
- Anthropic "be clear and direct" (motivated rules) —
  https://platform.claude.com/docs/en/docs/build-with-claude/prompt-engineering/be-clear-and-direct
- Anthropic output styles deprecation —
  https://docs.anthropic.com/en/docs/claude-code/output-styles
- Anthropic agent-skills engineering post (keep SKILL.md lean) —
  https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- Following Length Constraints in Instructions (word-budget overshoot) —
  https://arxiv.org/html/2406.17744
- YapBench (verbosity failure modes; newer models more verbose) —
  https://arxiv.org/html/2601.00624v1
- RLHF length bias — https://arxiv.org/pdf/2310.10076 and
  https://arxiv.org/abs/2511.12573 ; same bias in LLM judges —
  https://arxiv.org/html/2407.01085v3
- Community-grade (flagged as such): knightli.com verbose-output settings write-up —
  https://knightli.com/en/2026/07/10/claude-code-reduce-verbose-output-settings/ ;
  claude-token-efficient — https://github.com/drona23/claude-token-efficient ;
  negative-instruction analysis —
  https://eval.16x.engineer/blog/the-pink-elephant-negative-instructions-llms-effectiveness-analysis
