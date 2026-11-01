# Extraction rubric

The five layers `write-in-voice` **extract** derives per language, at Step E.3.
Behavioral patterns is the load-bearing one.

#### Lexical
- **Signature phrases** -- phrases or constructions that appear across multiple samples and feel idiosyncratic to the user. Quote 5-10 with the sample they came from.
- **Banned phrases** -- import by reference from `/humanize-text`'s negative lists. Do NOT duplicate the lists; point: "All banned-phrase lists are owned by `/humanize-text`. This profile inherits them."
- **Preferred substitutions** -- when the user reaches for what would be a banned phrase, what do they actually use? Derive from samples. Example: if humanize bans "additionally" and user samples consistently use "and", record `additionally -> and (user pattern)`.
- **Vocabulary register** -- signature word choices. Technical jargon they prefer. Slang. Code-switching habits. Neologisms.

#### Syntactic
Measure across all samples in the language. Report numbers, not adjectives.
- **Sentence length**: median (p50) and 90th percentile (p90) in words. Max sentence length seen.
- **Punctuation habits**: em-dash density per 100 words, comma frequency, semicolon use, parenthetical use, ellipsis use.
- **Paragraph length**: typical and max in sentences.
- **Burstiness**: variance in sentence length within paragraphs. High variance is human; low variance is AI. Note any paragraph with a one-word sentence next to a 30-word sentence.

#### Rhetorical
- **Openers**: how does the user start? Concrete observation? Thesis? Scene? Question? Provocation? Quote 2-3 sample openers verbatim.
- **Hedges**: when does the user soften? Phrases like "I think", "could be wrong but", "maybe" -- or do they not hedge at all? Note absence as well as presence.
- **Closers**: how does the user end? Abrupt? Recap? Punchline? One-line zinger? Anti-climax?
- **Self-correction**: does the user mid-stream revise themselves ("actually, no -- ...")? Note frequency.
- **Position-taking**: does the user state opinions plainly, or stay neutral and report?

#### Tonal (Nielsen Norman four sliders, 1-10 each)
For each, give a number AND a worked example from samples:
- **Formal <-> Casual** (1 = ultra-formal, 10 = ultra-casual)
- **Serious <-> Funny** (1 = serious, 10 = constantly humorous)
- **Respectful <-> Irreverent** (1 = deferential, 10 = pointed/blunt)
- **Enthusiastic <-> Matter-of-fact** (1 = breathless, 10 = deadpan)

Note any variation by register (e.g. "casual: 8/10 funny; technical: 3/10 funny").

#### Structural
- **Paragraph rhythm**: typical pattern across paragraphs. Short -> long -> short? Uniform? Tapering?
- **List vs prose ratio**: how often does the user use bullets or numbered lists? Per 1000 words.
- **Header patterns**: H2-only? Heavy hierarchy with H3/H4? No headers in shorter pieces?
- **Bold/italic use**: does the user emphasize? How often? For what (definitions, jargon, emphasis)?

#### Behavioral patterns (the load-bearing section)

Distill 5-10 *behavioral patterns* the user follows. Each pattern must be:
- **Testable** -- you can check whether a draft follows it.
- **Distinct** -- not a restatement of another pattern.
- **Derived** -- supported by at least 2 samples (cite them).

Examples of the form (these are illustrative; the actual patterns come from the user's samples):
- "Opens with a concrete observation, not a thesis"
- "States position before evidence"
- "Cuts conclusions; ends when the argument ends"
- "Specific numbers preferred to vague claims"
- "Uses self-correction mid-paragraph instead of pre-emptive hedging"
- "Single-sentence paragraphs allowed and used for emphasis"

Avoid adjectival patterns ("witty", "warm", "engaging"). They are useless for generation.
