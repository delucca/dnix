# Skill Quality Checklist

Distilled from "Agent Skills Best Practices" research. Use this to evaluate a generated skill before presenting it.

## Frontmatter

- [ ] `name` is kebab-case, no spaces, no capitals, max 64 chars
- [ ] `name` matches the directory name
- [ ] `description` states BOTH what the skill does AND when to use it
- [ ] `description` includes natural-language trigger phrases a user would actually say
- [ ] `description` is under 1024 characters
- [ ] `description` includes negative triggers ("Do NOT use for...") if the scope could be ambiguous
- [ ] No XML angle brackets in any frontmatter field
- [ ] `allowed-tools` lists only what the skill actually needs (not everything)
- [ ] `disable-model-invocation` is true for skills with side effects the user should control

## Body — Structure

- [ ] SKILL.md body is under 500 lines
- [ ] Leads with a one-sentence goal explaining what happens when the skill runs
- [ ] Instructions are step-by-step and imperative ("Analyze...", "Read...", "Generate...")
- [ ] No second-person narration ("You should...", "You will...")
- [ ] Concrete examples included where the output format matters
- [ ] Troubleshooting section for likely failure modes

## Body — Writing Quality

- [ ] Constraints explain the *why*, not just the *what* — reasoning over rigid MUSTs
- [ ] Consistent terminology throughout (one term per concept)
- [ ] No filler: no "comprehensive", "robust", "seamless", "leverage"
- [ ] No generic advice a linter would catch ("write clean code", "use trailing commas")
- [ ] Positive phrasing where possible ("Use named exports" > "Don't use default exports")

## Progressive Disclosure

- [ ] Reference material lives in `references/`, not inline in SKILL.md
- [ ] Large templates live in `assets/`, referenced by path
- [ ] Scripts for deterministic operations live in `scripts/`
- [ ] All file references use paths relative to the skill directory
- [ ] File references are one level deep (no deeply nested chains)

## Invocation and Tooling

- [ ] If the skill bundles scripts, dependencies are documented with install commands
- [ ] If the skill uses MCP tools, they are listed in `allowed-tools`
- [ ] `argument-hint` is set if the skill accepts arguments
- [ ] `$ARGUMENTS` or `$1`/`$2` placeholders are used for dynamic input

## Context Efficiency

- [ ] No "kitchen sink" — only load what the current step needs
- [ ] Stable values are hardcoded, not discovered dynamically each run
- [ ] No duplicate information that Claude can derive from the codebase
- [ ] Every line passes the test: "Would removing this cause Claude to make mistakes?"
