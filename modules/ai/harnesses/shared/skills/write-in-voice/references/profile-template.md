# Voice-profile template

The document `write-in-voice` **extract** writes at Step E.4. Copy this structure,
filling every placeholder from the corpus. Fenced as-is below so it can be lifted whole.

```markdown
---
extracted: YYYY-MM-DD
samples_count: <N>
registers_covered: [casual, explanatory, ...]
languages: [en, pt-br]
---

# <name> -- Voice Profile

Built from <N> samples across <M> registers and <K> languages on <date>.

Sample index:
- en/casual: <filename>
- en/explanatory: <filename>
- ...
- pt-br/casual: <filename>
- ...

Pairs with `/humanize-text`. This profile is positive (what the user does); humanize is negative (what to strip).

## English

### Lexical
[as extracted]

### Syntactic
[as extracted, with measured numbers]

### Rhetorical
[as extracted]

### Tonal
[as extracted with NN/G sliders + examples]

### Structural
[as extracted]

### Behavioral patterns
[5-10 patterns, each with sample citation]

## PT-BR

[same five sections, same depth]

## Cross-language patterns
[anything that holds across both languages]

## Known gaps
[registers without samples, languages with thin coverage]
```
