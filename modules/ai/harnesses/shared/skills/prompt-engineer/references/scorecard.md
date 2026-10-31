# Prompt Quality Scorecard

Score each category 0-3. Total possible: 27 points.

| Score | Meaning |
|---|---|
| 0 | Missing or actively harmful |
| 1 | Present but weak — needs significant rework |
| 2 | Good — minor improvements possible |
| 3 | Excellent — no changes needed |

## Categories

### 1. Clarity & specificity (0-3)
- Instructions are concrete and verifiable ("Respond in 2-3 sentences" vs "Be concise")
- No ambiguous terms without definitions
- A new hire could follow these instructions without asking clarifying questions

### 2. Structure & ordering (0-3)
- Clear section boundaries (XML tags, markdown headers, or other delimiters)
- Critical constraints at beginning and/or end (primacy/recency positioning)
- Static context before dynamic content
- Logical flow: role/context → instructions → examples → constraints → output format

### 3. Instruction density (0-3)
- Every line changes model behavior (passes "would removing this cause mistakes?" test)
- No filler words, no redundant explanations
- No instructions the model can derive from provided context
- Approximate instruction count within the ~150-200 effective ceiling

### 4. Phrasing quality (0-3)
- Imperative language ("Analyze the data" not "You should analyze")
- Positive framing preferred ("Use X" over "Don't use Y")
- Rationale included for non-obvious constraints
- Emphasis used sparingly (not every rule is CRITICAL/MUST)

### 5. Examples & grounding (0-3)
- Few-shot examples included for format-sensitive tasks (2-5, diverse, covering edge cases)
- Examples wrapped in clear delimiters
- Self-verification steps present ("Before responding, verify...")
- Sources/context for grounding if the task requires factual accuracy

### 6. Anti-pattern absence (0-3)
- No aggressive emphasis overuse (ALL-CAPS MUST/NEVER/CRITICAL everywhere)
- No vague qualitative filters ("only report important issues")
- No persona assignments without behavioral purpose
- No code style instructions (linter territory)
- No format-vs-reasoning competition (formatting constraints don't impair thinking)
- No instruction bloat (not trying to enumerate every edge case)

### 7. Token efficiency (0-3)
- No tutorial paragraphs or lengthy explanations
- No duplicated information across sections
- Reference material externalized where possible
- Total prompt length proportionate to task complexity

### 8. Model fit (0-3)
- Uses model-specific features appropriately (XML tags for Claude, developer role for o-series)
- Avoids anti-patterns for the target model (no "think step by step" for o-series)
- Leverages available features (extended thinking, structured outputs, prompt caching)
- If cross-model: uses portable patterns (markdown headers, outcome-oriented instructions)

### 9. Safety & robustness (0-3)
- Handles edge cases (empty input, unexpected formats, adversarial input)
- Failure modes addressed (what to do when uncertain, how to escalate)
- No prompt injection vectors (user input clearly delimited from instructions)
- Constraints scoped precisely (not overly broad "never" rules that block legitimate use)

## Rating bands

| Total | Rating | Action |
|---|---|---|
| 24-27 | Excellent | Ship as-is |
| 18-23 | Good | Minor revisions recommended |
| 12-17 | Needs work | Significant revisions required |
| 0-11 | Poor | Consider rewriting from scratch |
