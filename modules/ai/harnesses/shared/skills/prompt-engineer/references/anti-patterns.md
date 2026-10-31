# Prompt Anti-Patterns

Scan for each pattern. Quote the offending text and suggest a concrete fix.

## 1. Aggressive emphasis overuse
**Pattern**: Multiple ALL-CAPS directives (MUST, NEVER, CRITICAL, IMPORTANT, ALWAYS) throughout the prompt.
**Why it's harmful**: Overtriggers on newer models (Claude 4.x, GPT-4o+). When everything is critical, nothing is. Consumes the emphasis budget — reserve for at most 2-3 truly critical rules.
**Fix**: Rewrite in normal language. Use emphasis only for genuine safety rails or hard constraints.

## 2. Instruction bloat
**Pattern**: Long lists of edge cases, elaborate if-then rules, or enumerated exceptions.
**Why it's harmful**: LLMs follow ~150-200 instructions reliably. Each low-value rule dilutes every high-value rule equally. Bloated prompts suffer context rot.
**Fix**: Replace edge-case lists with 2-3 diverse few-shot examples that demonstrate handling. Let the model generalize.

## 3. Vague qualitative filters
**Pattern**: "Only report important issues", "focus on relevant information", "be thorough but concise".
**Why it's harmful**: Ambiguous thresholds produce inconsistent behavior. "Important" means different things to different runs.
**Fix**: Make filters concrete: "Report bugs that could cause incorrect behavior or data loss; omit pure style nits."

## 4. Persona without purpose
**Pattern**: "You are a world-class senior expert engineer with 20 years of experience."
**Why it's harmful**: Research (Zheng et al., 2024) shows personas don't improve factual accuracy. They add tokens without behavioral change.
**Fix**: Delete, or replace with a specific behavioral directive: "Analyze code for correctness bugs, not style issues."

## 5. Negation-only rules
**Pattern**: "Don't use default exports", "Never use var", "Do not include comments".
**Why it's harmful**: ~50% more violations than positive-phrased equivalents in testing. Negation tells the model what to avoid but not what to do instead.
**Fix**: Flip to positive: "Use named exports exclusively." Reserve negation for true prohibitions with no positive alternative.

## 6. Format-reasoning competition
**Pattern**: Strict formatting requirements imposed during the reasoning phase (JSON schema, tables, specific markdown structure while also requiring analysis).
**Why it's harmful**: Research (Deng et al., 2025) demonstrates that formatting and reasoning compete for model capacity. Strict format constraints actively impair thinking quality.
**Fix**: Separate reasoning from output. Let the model think in `<thinking>` tags, then format the final answer. Or apply formatting as post-processing.

## 7. Kitchen-sink system prompt
**Pattern**: System prompts exceeding ~3000 tokens of instructions, covering every conceivable scenario.
**Why it's harmful**: Reasoning degrades around 3000 tokens of instructions. Long prompts suffer from instruction attenuation — constraints in the middle get less attention.
**Fix**: Trim to essentials. Use progressive disclosure (load additional context via tools when needed). Move path-scoped rules to conditional loading.

## 8. Duplicated context
**Pattern**: Restating information that exists in provided documents, tool descriptions, or previous messages.
**Why it's harmful**: Wastes tokens and can introduce contradictions when the duplicate drifts from the source.
**Fix**: Delete the duplicate. Reference the source directly: "Follow the conventions described in the provided style guide."

## 9. Legacy prompting patterns
**Pattern**: "Let's think step by step", "Take a deep breath", explicit chain-of-thought scaffolding on frontier models.
**Why it's harmful**: Frontier models (2025+) reason internally. Manual CoT is redundant or harmful — on o-series models it actively degrades performance.
**Fix**: Delete manual CoT. Use the model's native thinking features (extended thinking for Claude, reasoning_effort for o-series). Give general guidance ("think thoroughly") rather than prescribed steps.

## 10. Stale model assumptions
**Pattern**: Prefilling assistant responses for Claude 4.6+, using `system` role for o-series models, hardcoding deprecated parameters.
**Why it's harmful**: Causes API errors or silently degrades output quality.
**Fix**: Check current model documentation. Claude 4.6+: no prefilling. O-series: use `developer` role. Follow current SDK patterns.

## 11. Missing input boundaries
**Pattern**: User input mixed directly into instruction text without delimiters.
**Why it's harmful**: Creates prompt injection vectors. The model may interpret user data as instructions.
**Fix**: Wrap user input in clear delimiters: `<user_input>`, triple backticks, or XML tags. Place instructions before and after the input boundary.

## 12. Unbounded output expectations
**Pattern**: No length, format, or scope constraints on model output.
**Why it's harmful**: Produces inconsistent output length and structure across runs. Makes downstream parsing unreliable.
**Fix**: Specify output contract: format, approximate length, required sections, and what to omit.
