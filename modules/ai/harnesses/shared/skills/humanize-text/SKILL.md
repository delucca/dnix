---
name: humanize-text
description: Rewrites AI text to read as the user wrote it, stripping em dashes and cliches in English/PT-BR. Use for humanize, de-AI. NOT for drafting new text (write-in-voice).
argument-hint: "[text, file path, or empty to use current draft]"
allowed-tools: Bash(cat *), Bash(wc *), Bash(grep *), Bash(file *), Bash(ls *), Read, Grep, Glob, Write, Edit
---

# Humanize

Take text that was produced with LLM help and rewrite it so a reader cannot tell a model was involved. Preserve the user's intent, argument, and information. Strip the signatures that RLHF bakes into every frontier model.

This skill is grounded in corpus research on editing AI-assisted text so it reads as human. Run `bilbo:recall` for that topic if you need depth on any rule below.

## When NOT to use this skill

- Drafting new text from scratch rather than cleaning up existing AI-assisted text — use `write-in-voice`.

## Core principle

**Detection is a losing game; editing is not.** Perplexity tools are biased against non-native writers and collapse under trivial edits. What survives is the structural RLHF scaffold: helpful, balanced, uplifting, abstract, tricolon-heavy, exec-summary-then-recap. A human writer is burstier, more opinionated, more specific, more willing to be unbalanced. Edit toward that.

**Preserve voice, not scaffold.** If the source was Claude-heavy, keep its prose-forward sentences and cut the therapeutic hedges. If ChatGPT-heavy, cut em dashes and contrastive reframes. If Gemini-heavy, flatten listicles into prose. Do not homogenize.

## When to use this skill

- User pasted or linked to AI-assisted text and wants it humanized.
- User is about to publish something (a post, an email, a doc) that passed through an LLM.
- User is drafting in this session and wants a pass-before-send review.
- User explicitly invokes `/humanize-text`.

## Step 1 - Gather the text

1. If `$ARGUMENTS` is a file path that exists, read it with the `Read` tool.
2. If `$ARGUMENTS` contains inline text, use it directly.
3. If `$ARGUMENTS` is empty, use the most recent substantial draft produced in this conversation. If nothing qualifies, ask: "What text should I humanize?"
4. Note the source format (markdown, plain text, email, chat). Preserve it.

## Step 2 - Detect language and register

1. **Language**: English or Portuguese. If mixed, process each block in its own language. If Portuguese, determine variety:
   - Default to **PT-BR** unless the text or user context indicates PT-PT.
   - Look for PT-PT markers (`ecrã`, `ficheiro`, `autocarro`, `casa de banho`, `estou a fazer`). If any appear and the user is PT-BR, flag them for replacement in Pass 3.
2. **Register**: casual (chat, DM), professional (email, internal doc), formal (public post, article), technical (spec, RFC). Read the first two paragraphs to infer. Do not push a casual message into formal register or vice versa.
3. **Probable source model** (optional but useful):
   - Heavy em dashes + contrastive reframes + "In conclusion" closer -> ChatGPT family.
   - Therapeutic softeners ("I hear you", "that makes sense", "let's unpack") + prose-forward + low bullet density -> Claude family.
   - Rigid H2/H3 + bold-leading bullets + ordered listicles -> Gemini family.
   - **U+202F present** -> OpenAI reasoning (o3, o4-mini, GPT-5 non-reasoning). Near-deterministic.

Record the inferred language, register, and probable model family. Use them to calibrate the edits in Pass 5.

## Step 3 - Pass 1: character-level screen

This is the cheapest pass and has near-zero false positives. Run it first.

Replace globally:

| Find                             | Replace with                              |
|----------------------------------|-------------------------------------------|
| `U+202F` (narrow no-break space) | regular space                             |
| `U+00A0` (non-breaking space) in prose contexts | regular space                   |
| `U+200B` (zero-width space)      | delete                                    |
| `—` (em dash, U+2014)            | comma, period, or colon (never parentheses) |
| `–` (en dash, U+2013) in prose   | hyphen or rewrite                         |
| `"` `"` (smart quotes)           | `"`                                       |
| `'` `'` (smart apostrophes)      | `'`                                       |
| `…` (U+2026)                     | `...`                                     |
| `•` `▪` `◦` `→` `✓` and other decorative symbols | markdown `-` or delete     |

**Em-dash budget: zero. Never emit an em dash in the output, under any circumstance.** Replace every single one with a comma, period, or colon, or restructure the sentence so none is needed. Do not substitute parentheses for it (that just trades one tell for another, see Pass 4). Even one em dash anywhere is a hard fail of this skill.

If you find `U+202F`, tell the user: "Detected U+202F (narrow no-break space). This is near-deterministic evidence of OpenAI reasoning output. Stripped."

## Step 4 - Pass 2: phrasal screen (English)

Kill or replace on sight. These are the durable post-2024 markers - the public mockery killed "delve" and "intricate," so these connectors and scaffolds are what remained and kept rising.

### Connectors and filler

| Kill                     | Replace with                                       |
|--------------------------|----------------------------------------------------|
| additionally             | also, and, or delete                               |
| furthermore / moreover   | also, or delete                                    |
| notably                  | delete                                             |
| importantly / significantly | delete                                          |
| particularly             | delete or `especially`                             |
| comprehensive            | full, complete, or delete                          |
| crucial                  | key, main, or delete                               |
| robust                   | solid, reliable, or delete                         |
| seamless                 | delete (almost always padding)                     |
| leverage (verb)          | use                                                |
| utilize                  | use                                                |
| ensure that              | make sure                                          |
| in order to              | to                                                 |
| a wide range of          | many, or delete                                    |

### Opener scaffolds - delete entirely

- "It's important to note that..." -> state the point directly
- "It's worth noting that..." -> state the point directly
- "In today's fast-paced world..." -> start with the substance
- "In the ever-evolving landscape of..." -> start with the substance
- "In this article/post, I will..." -> start with the substance
- "This document outlines..." -> start with the substance
- "Let me explain..." -> just explain

### Contrastive reframe

"It's not just X, it's Y" / "This isn't about X, it's about Y" / "More than X, this is Y."

Rewrite to a single positive claim. Pick Y and say it. If X and Y are both true, say both without the fake-opposition framing.

### Therapeutic register (Claude-heavy output)

- "I hear you" / "that makes total sense" / "completely valid" -> delete
- "Let's unpack this" / "let's dig into this" -> just do the thing
- Hedging softeners ("just", "simply", "gently") -> delete when they do not change meaning
- "You might consider..." -> "consider..." or "do..."

### Sycophancy openers

- "Great question!" / "That's a fantastic point!" / "Excellent observation!" -> delete, start with the answer

### Motivational adjectives

- cutting-edge, state-of-the-art, innovative, world-class, best-in-class, powerful, elegant, delightful, clean, modern, intuitive -> delete or replace with a concrete specific claim

### Faded but still flagged

- delve, intricate, meticulous, meticulously, commendable, showcasing, underscores, exhibit(s) -> present-day readers spot these instantly. Rewrite.

### Tricolon (rule-of-three)

"fast, reliable, and scalable" / "enhancing efficiency, improving accuracy, and reducing costs." LLM output is compulsively tripartite. Vary: cut to two, expand to four, or pick the one that matters.

### Closings

- "In conclusion..." / "To summarize..." / "Ultimately..." -> delete. If the conclusion is already in the body, delete. If it needs one more sentence, write one sharp one.
- "Let me know if you have any questions" / "Happy to discuss" / "Feel free to reach out" -> delete unless the context (email) genuinely needs a closing. Even then, keep it short and not AI-templated.

## Step 5 - Pass 3: phrasal screen (Portuguese)

Most PT-specific tells do not exist in English and are not caught by English-first tools. This pass is where the biggest gains come from for PT text.

### Variety contamination (highest-signal PT tell)

If target is **PT-BR**, replace PT-PT leakage:

| PT-PT leak        | PT-BR fix          |
|-------------------|--------------------|
| ecrã              | tela               |
| ficheiro          | arquivo            |
| rato              | mouse              |
| autocarro         | ônibus             |
| casa de banho     | banheiro           |
| facto             | fato               |
| telemóvel         | celular            |
| pequeno-almoço    | café da manhã      |
| comboio           | trem               |
| sumo              | suco               |
| frigorífico       | geladeira          |
| estou a fazer     | estou fazendo      |
| vou fazer         | vou fazer (same)   |

If target is **PT-PT**, flip direction and replace PT-BR gerúndio with infinitive (`estou fazendo` -> `estou a fazer`).

### Anglicismos (calques from English)

| Kill                               | Replace with                                 |
|------------------------------------|----------------------------------------------|
| endereçar um problema              | tratar, lidar com, resolver                  |
| entregar valor                     | gerar valor, trazer valor, or rewrite        |
| acionável                          | prático, aplicável, útil                     |
| alavancar                          | usar, aproveitar                             |
| suportar (no sentido de apoiar)    | apoiar (keep `suportar` only for "tolerate") |
| performar                          | ter desempenho, render                       |
| priorizar (ok) vs `deletar`        | prefer `excluir`, `remover`                  |
| Tenha um ótimo dia!                | Qualquer dúvida, estou à disposição.         |

### Clichéd openers and connectors

Kill outright:

- é importante ressaltar / é importante destacar
- vale destacar / vale ressaltar / vale mencionar
- no mundo atual / no cenário atual / no contexto atual
- em um mundo cada vez mais...
- dessa forma / desta forma (when padding)
- por fim / em suma (when recapping what was just said)
- além disso (over-used; vary with `e`, `assim`, `e também`, delete, or restructure)
- crucial (same kill as English)
- jornada (over-used in corporate-PT for "process" or "experience")

Over-formal connectors that no PT-BR writer actually uses:

- ademais, outrossim, destarte, sobremaneira -> delete or use `também`, `assim`, `portanto`

### Grammatical mannerisms

- **Gerundismo** ("vou estar enviando o relatório") -> simple future or near-future (`enviarei o relatório`, `vou enviar o relatório`). Telemarketing register; LLMs over-reproduce it in business prose.
- **Nominalization chains** (`-ção`/`-mento` piling: "a implementação da otimização do processamento") -> break into verbs (`implementamos X para otimizar o processamento`).
- **Passive voice** where impersonal `se` fits: `foi decidido que` -> `decidiu-se que` or `decidimos que`.
- **English-style capitalization**: PT orthography writes months, days, and languages in lowercase. Fix `Janeiro` -> `janeiro`, `Segunda-feira` -> `segunda-feira`, `Português` -> `português`.
- **Number formatting**: decimal comma, period-separated thousands (1.000,50). Flip any Anglicized `1,000.50` back.
- **Emphasis-verb pileups**: ressaltar / destacar / salientar / enfatizar / evidenciar / elucidar. Pick one per doc, use sparingly.
- **"Que ótima pergunta!"** / affirmation-first openers -> delete.

## Step 6 - Pass 4: structural critique

These are the hardest signals to edit and carry the most weight. Fix them or the text still reads as AI even after the word-level cleanup.

### Exec-summary opener

LLMs default to a bold-led first paragraph that previews the entire argument. Humans don't usually write that way in casual or medium-length prose; they lead with the point and let the body earn it.

- If the first paragraph restates everything the body says, cut it. Replace with a single sharp claim.
- If the first paragraph is bold-leading (`**bold sentence**. Then regular prose.`) and the bold sentence is a thesis, keep the thesis but unbold it unless the format (a report, a research piece) genuinely calls for bolding.

### Symmetric intro/outro

LLMs close by recapping the intro. Humans often just stop, or push one step further.

- If the last paragraph starts with "In conclusion", "To summarize", "Ultimately", or echoes the intro - delete it. If one sentence is needed to land the argument, write one sharp sentence that says something new.

### Tricolon compulsion

Count rule-of-three constructions. If there are more than two in a medium-length doc, rewrite at least one to a pair, a single item, or four items. Humans vary; LLMs triple.

### Sentence-length uniformity

LLMs produce tight sentence-length variance (Muñoz-Ortiz 2024). Measure roughly: do all sentences in a paragraph feel the same length? If yes, break one into a fragment and stretch another into a long one. Burstiness is the signal.

### Rigid H2/H3 + bold-leading bullets (Gemini-heavy)

Lists of bold-headed bullets where each bullet starts with a bold phrase and a colon:

```
- **Scalability**: the system handles...
- **Reliability**: the system recovers...
- **Performance**: the system maintains...
```

If the content is argumentative, restructure into prose. If the content is genuinely a list of parallel items, keep the list but unbold the labels and vary the sentence structure.

### Moralizing uplift ending

"Ultimately, X teaches us that..." / "At its core, this is about..." / "What matters most is..."

Delete. Humans don't wrap most writing with a moral. If the writer genuinely has a moral, it belongs as one terse sentence, not as a peroration.

### Pseudo-objective balance

"On one hand X, on the other hand Y, the truth likely lies in the middle." LLMs balance reflexively. Take a position. If both sides have merit, say so in one sentence and then say which you think is more right.

### Parenthetical asides (remove excessive parentheses)

LLM prose leans on parentheses to cram in asides, definitions, and hedges (often like this, mid-sentence, breaking the flow). Now that em dashes are banned, the temptation is to reach for parentheses instead. Do not. They are their own tell when overused.

Default to removing parentheses. For each parenthetical, pick one:

- **Fold it into the sentence** with commas if the aside is essential: `the API (which is rate-limited) returns...` -> `the API, which is rate-limited, returns...`
- **Promote it to its own sentence** if it carries real weight: `we shipped the fix (it cut latency by 40%)` -> `we shipped the fix. It cut latency by 40%.`
- **Delete it** if it is a hedge, a restatement, or padding: `the result (as expected) was positive` -> `the result was positive`.

Budget: at most one parenthetical per paragraph, and only when neither folding nor deleting reads better. Never nest parentheses. Never use a parenthetical to replace the em dash you just removed. Keep genuine technical uses (inline citations, code like `foo()`, units like `(ms)`, acronym expansions on first mention) as they are.

### Ordered-list overload

Numbered lists where prose would work better. Six-plus items at the same hierarchy level is usually a sign the content is argumentative, not enumerative.

## Step 7 - Pass 5: voice preservation

Now that the tells are stripped, check you haven't stripped the author too.

1. **Re-read the cleaned text as a whole.** Does it still sound like the same person? Does it still carry their opinion, their specificity, their examples?
2. **If the source had a strong voice** (informal phrasing, unusual metaphors, the user's own way of saying things), restore anything the edits flattened. Humanizing should not sand off the human.
3. **If the source had no voice** (pure AI output with no personalization), the cleaned text will read neutral-professional, not like the user wrote it. Flag this to the user: "Source had no personal voice to preserve. The cleaned version reads neutral-professional. If you want it to sound more like you, add a specific example, an opinion, or an unusual turn of phrase."
4. **Calibrate to register** (Step 2). A cleaned email should read like an email, not a blog post.

## Step 8 - Self-review checklist

Before returning the text, verify:

- [ ] No U+202F, U+200B, or other exotic whitespace.
- [ ] **Zero em dashes anywhere in the output. Not one.** Search the text for `—` and confirm it returns nothing.
- [ ] No excessive parentheses: at most one parenthetical per paragraph, none used to stand in for a removed em dash, none nested.
- [ ] No smart quotes, no Unicode ellipsis, no decorative bullets.
- [ ] No banned English connectors (additionally, furthermore, notably, etc.) unless genuinely needed.
- [ ] No opener scaffolds ("It's important to note", "In today's...", etc.).
- [ ] No contrastive reframes without a real opposition.
- [ ] No tricolon density above the doc's normal rhythm.
- [ ] No therapeutic softeners unless the register demands them.
- [ ] No sycophancy openers.
- [ ] No moralizing conclusion.
- [ ] **If PT**: no variety contamination, no anglicismos, no gerundismo in business prose, months/days/languages lowercase.
- [ ] Sentence-length variety: at least one short sentence and one long one per medium paragraph.
- [ ] No pseudo-objective balance where a position would be stronger.
- [ ] Length is comparable to the source. Do not pad. Do not truncate.
- [ ] The author's voice, examples, and opinions are intact.

If any check fails, revise before presenting.

## Step 9 - Output

Return in this format:

```
### Humanized text

<the full cleaned text, preserving the source format>

### Changes made

- Stripped <N> em dashes (replaced with commas/periods).
- <any U+202F/U+200B/other character findings - flag these first>
- Cut <phrase> in opener / body / closing.
- Rewrote contrastive reframe at paragraph <N>.
- <PT-specific: variety / anglicismos / gerundismo if applicable>
- <structural: exec-summary cut, tricolon varied, ordered list flattened to prose>

### Probable source model

<One sentence. E.g., "Heavy em-dash density and contrastive reframes suggest ChatGPT." Skip if inconclusive.>

### Still worth your attention

<Anything you flagged but did not edit because it needs a human judgment call: a tricolon that might be load-bearing, a section where you cut the conclusion and the argument might now feel abrupt, a PT-PT word you kept because you were not sure of the variety. Skip the section if there is nothing.>
```

Keep the "Changes made" list concrete and concise. One bullet per category of change, not per instance. Do not pad.

## Hard prohibitions

Never, as part of this skill:

- Add content that wasn't in the source. Humanizing is editing, not ghostwriting.
- Change the author's position or argument. If you think they're wrong, say so as a note, don't rewrite it.
- Replace specific claims with vague ones. "23% reduction in p99 latency" stays; do not smooth it to "significant performance gain."
- Strip technical precision to make prose flow. Domain terms stay.
- Pad length with filler. If the source is 200 words, the cleaned version is ~200 words, not 400.
- Truncate the source to look terser. Cut only what was AI padding.
- Use any banned phrase or character in your own output text (the change log, the notes).
- Claim the text is "now undetectable by AI detectors." Detectors are unreliable in both directions. Sell the craft, not the evasion.
- Apply English rules to Portuguese text or vice versa. Run the correct pass.
- Homogenize voice across model families. A Claude-sourced draft and a ChatGPT-sourced draft need different edits.
- Invoke other skills or MCP servers unless the user asks. This skill is self-contained.

## Proactive use (drafting mode)

If the user is **drafting** in the session rather than handing over finished text, invoke these rules preemptively as you write for them:

1. Avoid the banned opener scaffolds from the start.
2. Never write an em dash at all. Use a comma, period, or colon instead, and never reach for parentheses as the substitute.
3. Stop at any parenthetical and ask: "Can I fold this into the sentence with commas, promote it to its own sentence, or just delete it?" Default to one of those.
4. Stop at any tricolon and ask: "Does this need three?"
5. Stop at any "additionally" / "furthermore" / "além disso" and ask: "Is this connector earning its place?"
6. Avoid "In conclusion" / "Em suma" endings; end when the argument ends.
7. For PT text, default to PT-BR unless told otherwise, and check for gerundismo before submitting.

In drafting mode, you can skip the formal output format of Step 9 and just produce clean text. If the user asks to see what you avoided, summarize briefly.
