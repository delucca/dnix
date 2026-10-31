---
name: prompt-engineer
description: Crafts or reviews LLM prompts and skill or agent instructions, with a quality scorecard. Auto-triggers when writing skill or agent content.
argument-hint: "[create <topic> | review <file-or-selection>]"
allowed-tools: Bash(cat *), Bash(wc *), Bash(rg *), Bash(find *), Bash(ls *), Read, Write, Edit, Grep, Glob, AskUserQuestion, Skill(bilbo:recall), Skill(bilbo:reference)
model: opus
---

# Prompt Engineer

Craft or review LLM prompts grounded in curated best practices, producing output that follows Anthropic/OpenAI/Google guidance and passes a structured quality scorecard.

## When NOT to use this skill

- **Editing CLAUDE.md's structure or load hierarchy** (which files load when, instruction budget, `.claude/rules/` scoping) — use `edit-claude-md` instead. This skill judges the wording quality of instruction content; `edit-claude-md` owns where that content lives and how it loads.
- **Creating a new skill or agent from scratch** — use `create-skill` or `create-agent` instead. Those skills run the full interview-and-generate workflow; this skill only crafts or reviews the prompt text itself.

## Phase 1 — Determine mode

Parse `$ARGUMENTS` to determine the operating mode:

| Input pattern | Mode |
|---|---|
| `create <topic or description>` | **Create** — draft a new prompt from scratch |
| `review <file path or pasted text>` | **Review** — audit an existing prompt |
| No arguments, but currently editing a SKILL.md / AGENT.md / CLAUDE.md | **Review** — audit the instruction content being written |
| Ambiguous | Ask the user via `AskUserQuestion` |

## Phase 2 — Ground in best practices

Before drafting or reviewing, query the metaprompting library sources through `bilbo:reference` to load relevant best practices for the specific prompt type being created or reviewed.

Craft a targeted question based on the prompt type and run it via `bilbo:reference`, then read its cited answer:

- **System prompt**: "What are the best practices for structuring LLM system prompts? Cover: instruction hierarchy, XML tags, section ordering, constraint setting, instruction budget."
- **Tool description**: "What are the best practices for writing tool descriptions for LLM function calling? Cover: description length, when-to-use guidance, parameter naming, error handling."
- **Skill/agent instructions**: "What are the best practices for writing agent or skill instruction files? Cover: progressive disclosure, imperative language, few-shot examples, constraint phrasing."
- **CLAUDE.md content**: "What are the best practices for CLAUDE.md instruction content? Cover: instruction density, pruning heuristics, positive phrasing, rationale inclusion."
- **General/other**: "What are the key principles for effective prompt engineering? Cover: clarity, specificity, examples, structure, common anti-patterns."

Keep what those sources say as grounding context for subsequent phases. If no library source covers the topic, note the gap and proceed on general best-practice judgment.

## Phase 3 — Create mode

Skip to Phase 4 if mode is Review.

### 3a — Gather requirements

Use `AskUserQuestion` to fill gaps. Adapt to what `$ARGUMENTS` already provides — do not over-interview.

Gather:
- **Target model**: Claude, GPT, Gemini, or multi-model? (defaults to Claude)
- **Prompt type**: system prompt, tool description, agent instructions, skill body, CLAUDE.md section, or other
- **Purpose**: what task the prompt enables (concrete, not "help with X")
- **Audience**: who will interact with the prompted model (end users, developers, other agents)
- **Output expectations**: what format and style the prompted model should produce
- **Constraints**: hard rules, safety rails, things the model must never do
- **Context**: reference material, examples, or existing prompts to build from

### 3b — Draft the prompt

Apply these principles (grounded in library context from Phase 2):

**Structure:**
- Lead with role/context in one sentence, not a paragraph
- Use XML tags for Claude, markdown headers for cross-model portability
- Place static reference material before dynamic content
- Put critical constraints at the beginning and end (primacy/recency bias)
- Separate reasoning space from output space when the task requires thinking

**Instruction quality:**
- Imperative language ("Analyze the input", not "You should analyze")
- Positive phrasing ("Use named exports" over "Don't use default exports")
- Include rationale for non-obvious constraints ("Keep under 200 lines because instruction compliance degrades past ~150 instructions")
- Concrete over vague ("Respond in 2-3 sentences" over "Be concise")
- Tell the model what TO do, not what NOT to do

**Examples and grounding:**
- Include 2-3 diverse few-shot examples for format-sensitive tasks
- Wrap examples in `<example>` tags (Claude) or clear delimiters
- Show edge cases in examples, not in rule lists
- Add self-verification steps ("Before responding, verify X, Y, Z")

**Token efficiency:**
- Every line must pass: "Would removing this change the model's behavior?"
- No filler words ("comprehensive", "robust", "leverage", "seamless")
- No persona preambles unless they serve a specific behavioral purpose
- No code style instructions (use linters)
- No information the model can derive from provided context

**Model-specific optimizations:**
- Claude: use XML tags, adaptive thinking, avoid aggressive emphasis (MUST/CRITICAL/NEVER in all-caps)
- GPT reasoning models (o-series): keep prompts simple and goal-oriented, avoid step-by-step instructions, use `developer` role
- Gemini: explicit modality references, keep temperature at default
- Cross-model: use markdown headers as universal delimiters, outcome-oriented instructions

### 3c — Present the draft

Show the full drafted prompt to the user. Proceed to Phase 5 (library deep review).

## Phase 4 — Review mode

### 4a — Load the prompt

Read the target prompt from the provided file path, pasted text, or current editing context.

### 4b — Score against the quality scorecard

Read the scorecard criteria:

```
Read references/scorecard.md from this skill's directory
```

Evaluate the prompt against each criterion. Assign scores (0-3) per category.

### 4c — Scan for anti-patterns

Read the anti-patterns list:

```
Read references/anti-patterns.md from this skill's directory
```

Flag every match with the offending text quoted and a specific fix suggestion.

### 4d — Present the review

Output format:

```
## Prompt Review

### Scorecard
| Category | Score | Notes |
|---|---|---|
| Clarity & specificity | 0-3 | ... |
| Structure & ordering | 0-3 | ... |
| ... | ... | ... |
| **Total** | **/27** | |

### Anti-patterns found
1. [pattern name] — "[offending text]" → [fix]
2. ...

### Structural suggestions
- [suggestion with rationale]

### Strengths
- [what the prompt does well]
```

Proceed to Phase 5 (library deep review).

## Phase 5 — Library deep review

After drafting (create mode) or scoring (review mode), review the prompt against the metaprompting library sources for an expert-level review.

### 5a — Submit for review

Invoke `bilbo:reference` with a query naming the prompt type, read its cited answer, then review the full prompt against it using this review question:

> "Review this LLM prompt for quality and best practices compliance. Evaluate: clarity and specificity of instructions, structural organization (ordering, delimiters, hierarchy), anti-patterns (instruction bloat, aggressive emphasis, vague constraints, format-vs-reasoning competition, persona overuse, negation-only rules), token efficiency, few-shot example quality, model-specific considerations, and grounding/verification steps. Identify specific issues and suggest concrete fixes. Here is the prompt: [full prompt content]"

### 5b — Synthesize library feedback

Cross-reference the library review with your own scorecard (review mode) or draft assessment (create mode). Identify:
- Where the library and your analysis agree (high-confidence findings)
- Where they disagree (present both perspectives to the user)
- New issues the library review caught that you missed

### 5c — Present combined results

For **create mode**: show the draft, your assessment, and library findings. Recommend specific revisions and ask which to apply.

For **review mode**: append the library review section to the scorecard:

```
### Library Expert Review
[Synthesized findings from the metaprompting library sources]

### Combined Recommendations (prioritized)
1. [highest-impact fix] — confidence: high (both analyses agree)
2. [next fix] — ...
```

### 5d — Apply revisions

If the user approves changes:
1. Apply each revision, stating the rationale
2. Re-score the modified prompt against the scorecard
3. Show before/after scores

### 5e — Library miss protocol

If `bilbo:reference` finds no library source on the topic:
1. Note that the library deep review was skipped — there is no external fallback to retry.
2. Present results without the library review, noting it was skipped.

## Hard prohibitions

- Never draft a prompt without querying the library sources first (Phase 2) - ungrounded drafts drift toward generic patterns that ignore model-specific guidance and repeat common mistakes the sources already document
- Never present a review without the scorecard — qualitative feedback without scores gives the user no way to prioritize fixes or measure improvement after revisions
- Never skip the library deep review (Phase 5) unless no metaprompting library source exists, in which case note the gap - the library holds curated sources covering edge cases and anti-patterns that a checklist alone cannot catch
- Never use aggressive emphasis (ALL-CAPS MUST/NEVER/CRITICAL) in drafted prompts — Anthropic's Claude 4 docs confirm it overtriggers on newer models, and overusing emphasis makes every rule equally weighted, defeating the purpose
- Never add persona preambles ("You are a world-class expert") without a specific behavioral reason — Zheng et al. (2024) tested 2,410 questions and found personas do not improve factual accuracy; use concrete behavioral directives instead
- Never include code style instructions in prompts — linters enforce deterministically, cheaply, and consistently; prompting for style wastes instruction budget on something a tool does better
- Never fabricate library review feedback — if the review was not performed, say so explicitly; fabricated feedback is indistinguishable from grounded feedback and erodes trust
- Never loop when `bilbo:reference` finds no library source for this topic - accept it and proceed, noting the gap
