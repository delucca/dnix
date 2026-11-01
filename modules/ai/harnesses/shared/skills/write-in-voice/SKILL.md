---
name: write-in-voice
description: Drafts new text in the user's voice from a topic or notes, then humanizes it. Use for write as me, draft in my voice. NOT for cleaning existing text (humanize-text).
argument-hint: "[topic | prompt | file path | 'prompt-me' | 'extract' | 'add <register>'] [--raw]"
allowed-tools: Bash(cat *), Bash(wc *), Bash(grep *), Bash(ls *), Bash(date *), Bash(mkdir *), Bash(stat *), Bash(git *), Read, Grep, Glob, Write, Edit, Skill, AskUserQuestion
---

# Write As Me

Take a topic, prompt, or rough notes and draft text the way the user would write it. Built on a stored voice profile + register-matched exemplars + `/humanize-text` as a final pass, not generic "sound human" prompting.

## When NOT to use this skill

- Cleaning up existing AI-assisted text rather than drafting something new — use `humanize-text` (see "Pairing with /humanize-text" below for how the two fit together).

This skill pairs with `/humanize-text`:
- `/write-in-voice` is the **positive** layer (drafts in voice).
- `/humanize-text` is the **negative** layer (strips AI tells from the draft).
- Default: `/write-in-voice` invokes `/humanize-text` automatically as the final step. Pass `--raw` to skip.

## Storage

The voice data lives outside the skill, in a corpus directory the user owns. Read `~/.config/ai/settings/write-in-voice.json` first: its `corpus` field is that directory's absolute path, written `$CORPUS` below. If the file or the field is missing, stop and tell the user to set `dnix.ai.skills.write-in-voice.settings.corpus`.

```
$CORPUS/
├── profile.md                  (extracted voice profile)
├── profile-archived-<date>.md  (older profiles, kept for diffing)
└── samples/
    ├── <date>--en-casual--<slug>.md
    ├── <date>--pt-br-technical--<slug>.md
    └── ...
```

The skill reads and writes `$CORPUS` directly. When it sits in a git work tree (`git -C "$CORPUS" rev-parse --show-toplevel` succeeds), every write is staged with `git -C "$CORPUS" add <path>`; otherwise skip the staging steps and the commit reminders. The skill never commits: the user reviews and commits.

## Core principle

**Profile + exemplars beats either alone.** A persistent voice profile gives consistency. 2-3 register-matched exemplars at generation time give specificity. Profile-only loses ~20% fidelity; exemplars-only drifts across sessions.

**Behavioral patterns over adjectives.** "Opens with a concrete observation, not a thesis" works. "Engaging, witty, warm" collapses to generic across all users. The profile records *what the user does*, not *what kind of writer they are*.

**Sample by register, not by recency.** Five LinkedIn posts produce a voice that can only write LinkedIn posts. The corpus must cover casual, explanatory, frustrated/critical, persuasive, and technical -- per language.

**Don't fabricate the takes.** This skill writes the words. The user supplies the substance: opinions, positions, examples, claims. If a draft needs a position the user has not stated, ask. Do not invent.

**Two-pass output.** Drafting in voice (positive) + humanize cleanup (negative) is the published workflow. Do both unless `--raw` is set.

## When to use

- User asks to "write as me", "draft this in my voice", "ghostwrite", "make this sound like me".
- User passes a topic or rough notes and wants a first draft in their voice.
- User invokes `/write-in-voice`.
- User invokes `/write-in-voice prompt-me` (interview-style sample collection -- works for first-run or for adding samples later) or `/write-in-voice extract` / `add <register>` (other corpus updates).

If no profile exists when a draft is requested, run `prompt-me` first. Do not fake it.

## Argument parsing

The first non-flag token selects the mode. The `--raw` flag (anywhere in args) skips the humanize pass.

| Token                          | Mode      | Action                                                  |
|--------------------------------|-----------|---------------------------------------------------------|
| `prompt-me`                    | prompt-me | Interview-style sample collection. Asks curated questions, saves answers. Works for first-run AND for adding samples later when drafts feel weak. |
| `init`                         | prompt-me | **Backward-compat alias.** Prints a one-liner ("`init` was renamed to `prompt-me`. Running prompt-me now…") and proceeds into prompt-me mode. |
| `extract`                      | extract   | Re-extract profile from existing samples on disk.       |
| `add <register>`               | add       | Add a single existing piece (paste or file path) to a specific register. |
| anything else (or empty)       | draft     | Draft text in voice from the topic, prompt, or notes.   |

The `--raw` flag only applies in draft mode. It is ignored elsewhere.

---

## Mode 1: prompt-me -- interview to gather samples

Question-driven sample collection. **Replaces the old `init` mode.** The same command works for first-run setup AND for adding more samples later when drafts feel weak -- no separate "init" step.

The agent asks one question at a time, the user answers naturally in chat, the agent saves the answer as a register-tagged sample. No paste burden, no "go find your old writing" friction. The user can `skip` any question or type `done` to stop the interview.

### Step P.1 -- Backward-compat alias + detect bootstrap vs expand

If `$ARGUMENTS` is exactly `init`, print this first (then continue with the prompt-me flow):

> `init` was renamed to `prompt-me`. Running prompt-me now…

Detect mode:

```bash
ls $CORPUS/samples/*.md 2>/dev/null | wc -l
```

If 0 samples -> **bootstrap** (Step P.2a).
If 1+ samples -> **expand** (Step P.2b).

### Step P.2a -- Bootstrap setup

Tell the user verbatim:

> I'll gather writing samples by asking you questions, one at a time. Answer the way you naturally would in chat or DM -- don't perform, don't dress it up. Type `skip` to pass on a question. Type `done` whenever you've had enough. I'll save each answer to your corpus as we go.

Then ask via `AskUserQuestion`:

> Which languages do you write in?

Options: `en`, `pt-br`, `both`.

For each chosen language, ask once via `AskUserQuestion` (multiSelect: true):

> Any registers to skip up front? (You can also skip individual questions later.)

Options: `casual`, `explanatory`, `frustrated/critical`, `persuasive`, `technical`. Default: none selected (skip nothing).

Build the slot list of `(lang, register)` pairs from what's left. Order them to alternate within each language so the user does not fatigue on one register: casual -> explanatory -> frustrated -> persuasive -> technical. If both languages are chosen, alternate across languages too (one EN slot, one PT-BR slot, one EN, one PT-BR, ...).

Tell the user the plan: "I'll work through <N> questions total." Proceed to Step P.3.

### Step P.2b -- Expand setup

Read existing profile metadata and list samples by register/language:

```bash
head -10 $CORPUS/profile.md 2>/dev/null
ls -1 $CORPUS/samples/*.md
```

Tell the user:

> You have <N> samples and a profile extracted on <date>. What do you want to add to?

Use `AskUserQuestion`:
- "A specific register/language" (you tell me which)
- "Drafts have been getting something wrong" (you describe what; I infer the weak register)
- "Coverage gap" (I pick the register x language with the thinnest coverage)
- "Surprise me" (I pick what feels useful given the corpus)

Resolve to a list of `(lang, register)` slots:
- `specific` -> ask the user which slot(s).
- `symptom` -> ask the user to describe what drafts get wrong; map their description to a register x language (e.g. "drafts in PT-BR feel too stiff" -> casual PT-BR; "technical writing sounds generic" -> technical EN/PT depending on language they write tech in).
- `coverage gap` -> count samples per `(lang, register)` cell; pick the lowest-count cells.
- `surprise me` -> pick a cell missing from the corpus, or the cell with the oldest sample.

Proceed to Step P.3.

### Step P.3 -- Ask, save, loop

For each `(lang, register)` slot in order:

#### P.3.1 -- Pick a question

1. Glob existing samples for this slot:
   ```bash
   ls $CORPUS/samples/*--<lang>-<register>--*.md 2>/dev/null
   ```
2. Read each one's `prompt:` frontmatter field. Collect all previously-asked questions for this slot.
3. From the **Question Bank** (next major section), pick the first question for this slot whose text is NOT in the asked list.
4. If all bank questions for this slot are exhausted, generate one in the same spirit (provokes the target register, leans on real experience, self-contained, answerable in 100-300 words). Tell the user: "(bank exhausted for this slot -- generated a fresh question.)"

#### P.3.2 -- Ask the question

Frame in chat exactly:

```
Sample <N> of <M> | register: <register> | language: <lang>

Q: <the question>

(Answer naturally. `skip` to skip, `done` to stop the interview.)
```

#### P.3.3 -- Wait for the user's reply

- `skip` (case-insensitive, exact word) -> record nothing for this slot, move to the next.
- `done` (case-insensitive, exact word) -> break the loop, jump to Step P.4.
- Anything else -> treat the entire message as the sample answer.

#### P.3.4 -- Adaptive follow-up (optional)

Fire only if BOTH conditions hold:
- Register is `explanatory`, `persuasive`, `frustrated`, OR `technical` (skip the follow-up for `casual` -- short casual answers are fine).
- Answer is shorter than ~60 words.

Frame:

```
Quick follow-up: <one specific probe drawn from the answer -- not generic>. A few more sentences is fine.
```

Be specific ("you mentioned X -- what's the sharpest version of that?"), not generic ("can you say more?"). Anchor the probe in something the user actually wrote, not in the original question.

If the user replies, concatenate as the sample body:

```
<original answer>

<follow-up answer>
```

If the user replies `skip` to the follow-up, save the original answer alone.

#### P.3.5 -- Save the sample

Filename:

```
$CORPUS/samples/<DATE>--<lang>-<register>--<slug>.md
```

`<slug>` is a short kebab-case label derived from the question (e.g., `weekend-recap`, `tool-pitch`, `bug-rca`). Pick something descriptive enough to scan-read filenames at a glance. If a file with that exact name already exists, append `-2`, `-3`, etc.

Frontmatter:

```yaml
---
date: YYYY-MM-DD
lang: en | pt-br
register: <register>
source: prompt-me
prompt: "<the question that was asked, verbatim, including the follow-up if any>"
---
```

Body: the user's answer (with follow-up appended if applicable). Untouched -- no editing, no cleanup, no "improvements." Samples are reference material; tampering with them poisons the corpus.

#### P.3.6 -- Stage it

```bash
git -C "$CORPUS" add samples/<filename>
```

#### P.3.7 -- Check-in (every 3 saved samples)

After every 3rd successfully saved sample, pause and ask via `AskUserQuestion`:

> <N> samples saved so far. Keep going (next: <next register/lang>), wrap up, or show me what we have?

Options: `keep going`, `wrap up`, `show me what we have`.

- `keep going` -> continue the loop.
- `wrap up` -> jump to Step P.4.
- `show me what we have` -> list the saved sample files (filename + register + lang + first 60 chars of the question), then ask again.

Don't check in after every single sample (annoying); don't go silent for 10+ samples in a row (also annoying).

### Step P.4 -- Wrap up

Tell the user:

> Saved <N> new samples in <list of register x lang slots, comma-separated>. Want me to extract a fresh profile now?

Use `AskUserQuestion`:
- "yes -- extract now" -> invoke Mode 2 (extract). The wrap-up commit reminder will then come from Mode 2's final step instead of here.
- "no -- I'll run /write-in-voice extract later" -> skip extraction; surface the commit reminder below.

Commit reminder (only when extraction is skipped):

> Samples saved and staged. To keep them:
>
> ```
> git -C "$CORPUS" commit -m "add voice samples"
> ```
>
> I have not committed automatically -- review the diff first if you want.

---

## Question Bank

Curated starter questions, five per `(register, language)` slot, plus the design
rules for generating fresh ones. Read `references/question-bank.md` when you reach
Step P.3.1 -- not before.

---

## Mode 2: extract -- re-extract the profile from existing samples

Reads every sample on disk and derives a fresh voice profile. Used after a `prompt-me` interview, an `add` import, or whenever the profile is stale (your writing has drifted from what the corpus reflects -- in which case add new samples first).

### Step E.1 -- Inventory samples

```bash
ls $CORPUS/samples/*.md 2>/dev/null
```

If zero samples, stop:

> No samples found. Run `/write-in-voice prompt-me` to gather some first.

**Minimum viable corpus: 4 samples covering at least 2 registers and 1 language.** If the corpus is below this threshold, warn but continue: "Below minimum corpus. Profile will be weak. Recommended: at least 4 samples, ideally 8+."

### Step E.2 -- Archive the existing profile (if any)

```bash
DATE=$(date +%Y-%m-%d)
if [ -f $CORPUS/profile.md ]; then
  mv $CORPUS/profile.md $CORPUS/profile-archived-${DATE}.md
  git -C "$CORPUS" add profile-archived-${DATE}.md
fi
```

### Step E.3 -- Extract per language

Read every sample. For each language present in the corpus, extract five layers --
Lexical, Syntactic, Rhetorical, Tonal, Structural. Read
`references/extraction-rubric.md` for what each one covers and for the
behavioral-patterns rules, which are the load-bearing part.

### Step E.4 -- Write the profile

Write to `$CORPUS/profile.md`, following the
structure in `references/profile-template.md` -- copy it whole and fill every
placeholder from the corpus.

Then stage it:

```bash
git -C "$CORPUS" add profile.md
```

### Step E.5 -- Commit reminder

Tell the user:

> Profile rewritten and staged. To keep it:
>
> ```
> git -C "$CORPUS" commit -m "refresh the voice profile"
> ```
>
> I have not committed automatically -- review the diff first if you want.

---

## Mode 3: add -- add a single sample (paste or file)

Use this when you already have a written piece you want to include verbatim (e.g., an existing Substack draft, an old email, a PR review). For agent-driven sample collection, use `prompt-me` instead.

`$ARGUMENTS` is `add <register>` or `add <register> <lang>` (default lang = en).

1. Confirm: "Adding a `<register>` sample in `<lang>`. Paste the sample, or give me a file path."
2. Save to `$CORPUS/samples/<YYYY-MM-DD>--<lang>-<register>--<slug>.md` (same `--<slug>` naming as `prompt-me`, where `<slug>` is a short kebab-case description of the sample) with frontmatter:
   ```yaml
   ---
   date: YYYY-MM-DD
   lang: en | pt-br
   register: casual | explanatory | frustrated | persuasive | technical
   source: <user description e.g. "DM to friend", "Substack draft", "code review on PR #1234">
   ---
   ```
   Body: the raw sample text, untouched.
3. Run `git -C "$CORPUS" add <path>`.
4. Tell the user: "Sample saved and staged. Run `/write-in-voice extract` to refresh the profile."

Do not auto-extract. Adding samples should be cheap; extraction is the deliberate step.

Note: `prompt-me` samples carry an additional `prompt:` frontmatter field recording the question asked. `add` mode samples omit it (no question).

---

## Mode 4: draft -- draft text in voice (default)

### Step 4.0 -- Parse arguments

Scan `$ARGUMENTS` for the `--raw` flag. If present:
- Set `RAW=true`.
- Strip `--raw` from the prompt.

The remaining text is the draft prompt.

### Step 4.1 -- Load the profile

```bash
cat $CORPUS/profile.md 2>/dev/null
```

If no profile exists, stop:

> No voice profile found at $CORPUS/profile.md. Run `/write-in-voice prompt-me` first to gather samples and extract a profile.

### Step 4.2 -- Identify language and register

**Language**: explicit user instruction wins ("write me a tweet in PT"). Otherwise infer from the prompt's own language. Otherwise default to EN unless the corpus has more PT samples.

**Register** (infer from the prompt):
- "tweet", "DM", "text my friend", "slack message", "chat" -> casual
- "blog post", "essay", "explainer", "doc", "email", "newsletter" -> explanatory
- "rant", "complaint", "critique", "callout", "vent" -> frustrated
- "pitch", "proposal", "argue", "convince", "make the case" -> persuasive
- "spec", "RFC", "ERD", "code review", "technical doc", "design doc" -> technical
- Ambiguous -> ask one clarifying question, then proceed.

### Step 4.3 -- Pick exemplars

Glob 2-3 sample files matching the chosen language + register:

```bash
ls -1 $CORPUS/samples/*--<lang>-<register>*.md 2>/dev/null
```

Read them in full -- do not summarize.

If no samples exist for that exact combination, fall back to the closest register and tell the user: "No `<register>` samples in `<lang>`. Falling back to `<closest>`. Output may drift toward that register's patterns."

If no samples exist in the requested language at all, stop:

> No `<lang>` samples in the corpus. Cannot draft in `<lang>`. Run `/write-in-voice add <register> <lang>` to seed the language, then retry.

### Step 4.4 -- Construct the internal prompt

In your reasoning, assemble:
1. The full voice profile (do not summarize -- the syntactic measurements and behavioral patterns matter).
2. 2-3 exemplars, full text, labeled with their register.
3. The task: what to write, what substance to include.
4. Register and length constraints (match the request).

This is not a tool call -- it is the context you generate against.

### Step 4.5 -- Draft

Generate the text. Critical rules during generation:

**No banned phrases.** Even though `/humanize-text` will run after, draft cleanly the first time. Watch for the top tells from `/humanize-text`:
- em-dash (more than ~1 per 150 words)
- "additionally", "furthermore", "moreover", "notably", "importantly"
- "It's important to note", "It's worth noting"
- "It's not just X, it's Y" (contrastive reframe)
- tricolons -- compulsive "X, Y, and Z" three-item lists
- "In conclusion", "Ultimately", "At its core", "What matters most"
- therapeutic softeners ("I hear you", "let's unpack", "completely valid")
- "Great question!", "That's a fantastic point!" (sycophancy)
- PT-BR: "é importante ressaltar", "vale destacar", "no mundo atual", "dessa forma"
- PT-BR: gerundismo ("vou estar enviando", "estaremos verificando")

**Match the syntactic profile.** If the profile says median sentence length is 14 words, do not generate paragraphs of all 30-word sentences. Match the burstiness.

**Re-anchor every ~400 tokens.** For drafts longer than 500 tokens, mid-generation re-read the profile's *behavioral patterns* and *tonal* sections. RLHF drifts the voice toward neutral after ~400 tokens.

**Burstiness.** Mix one short fragment and one long sentence per medium paragraph.

**Don't fabricate substance.** If the user gave a 3-bullet brief, do not invent a 5th claim. If you need a position the user has not stated, ask before writing it. If you need a number, statistic, or example you cannot verify, mark it as a placeholder (`<TODO: confirm>`) and surface it in the output.

### Step 4.6 -- Self-check (light pass)

Before invoking humanize, run a fast scan for the obvious misses:

- [ ] Em-dash count vs word count (target: <=1 per 150 words).
- [ ] No banned phrases from the top-10 list.
- [ ] At least one short and one long sentence per medium paragraph.
- [ ] No fabricated positions or invented examples.

If any check fails, revise before passing to humanize.

### Step 4.7 -- Run humanize (unless --raw)

If `RAW=false`:

1. Invoke `/humanize-text` via the Skill tool, passing the draft from Step 4.5.
2. Capture the cleaned text and humanize's change log.
3. Use the cleaned text as the final draft.

If `RAW=true`, skip this step. The output goes straight from 4.5/4.6 to 4.8.

### Step 4.8 -- Output

Return in this format (with humanize):

```
### Draft

<the humanize-cleaned text, in the requested format>

### Notes

- Register: <casual / explanatory / frustrated / persuasive / technical>
- Language: <EN / PT-BR>
- Exemplars used: <filenames or short labels>
- Length: <N words>
- Profile version: <extracted date from profile.md frontmatter>

### Humanize edits

<concise summary of what humanize changed -- one bullet per category, not per instance.
e.g. "Stripped 2 em dashes (replaced with periods). Cut 'Additionally' opener.
Flattened tricolon in paragraph 3.">

### Worth your attention

<Anything you flagged but did not fix because it needs the user's judgment: a position
you inferred and want them to confirm, a placeholder for an unverified claim, a register
fallback if no exact match existed. Skip this section if there's nothing.>
```

If `--raw` was passed, skip the **Humanize edits** section and add a one-liner: `*Raw output -- humanize pass skipped. Run `/humanize-text` if you want it cleaned.*`

---

## Hard prohibitions

Never, as part of this skill:

- Fabricate the user's positions, opinions, examples, or experiences. Ask if you need substance you do not have.
- Use any banned phrase from `/humanize-text`'s negative lists in the drafted output (or in your own meta-text in the Notes section). Humanize will catch them, but draft cleanly the first time anyway.
- Skip humanize when not in `--raw` mode. The default is the two-pass workflow; honoring it is non-optional.
- Auto-commit the corpus. The skill writes files and stages them with `git add`, but never `git commit` or `git push`. The user reviews and commits.
- Replace behavioral patterns with adjectives in the profile ("witty, warm, direct" -> useless for generation).
- Generate writing samples *for* the user during `prompt-me`. Samples are theirs; the whole skill collapses if the corpus is AI-generated.
- Invent or paraphrase the user's answer to a `prompt-me` question. If they `skip`, the slot stays empty. If their answer is short, ask a follow-up -- don't pad.
- Skip the register protocol in `prompt-me`. "Just give me 5 random samples" produces a sample-biased voice that can only write one register.
- Drift to RLHF mean. Re-anchor mid-generation for long drafts.
- Homogenize across languages. The EN profile and the PT-BR profile are independent and may differ on every layer.
- Inflate length. If the request implies 200 words, deliver ~200 words, not 500.
- Touch the profile or sample files during draft mode. Read-only.
- Strip technical precision to make prose flow. Domain terms stay.
- Edit existing samples to "improve" them. Samples are reference material -- they must remain unedited.

---

## Pairing with /humanize-text

| Layer        | /write-in-voice                                  | /humanize-text                              |
|--------------|-----------------------------------------------|----------------------------------------|
| Direction    | Positive (what to do)                         | Negative (what to strip)               |
| Input        | Topic, prompt, notes                          | Existing text (yours or AI-assisted)   |
| Output       | A draft in the user's voice                   | A cleaned version of the input         |
| When to use  | Generating new text                           | Cleaning existing text                 |
| Owns         | Voice profile, sample corpus                  | Banned-phrase lists, structural fixes  |

In the default workflow, `/write-in-voice` invokes `/humanize-text` automatically as Step 4.7 -- the user gets the published-ready draft in one call. The `--raw` flag preserves the manual workflow when you want to inspect the unedited draft, edit it yourself, then run `/humanize-text` separately.

`/humanize-text` remains usable standalone for any text the user did not draft via this skill (existing docs, AI output from elsewhere, hand-written drafts).

Do not duplicate humanize's banned lists in this skill or in the profile. Reference them by pointer. If humanize's lists change, this skill picks up the change for free.

---

## Evaluation (offline, optional)

Want to measure whether the skill's output actually sounds like you? Three approaches the research supports:

- **Burrows' Delta on function-word frequency.** Content-independent stylistic distance. Lower Delta = closer style. Standard in stylometry.
- **Self-blind test.** Wait 48 hours. Mix 3 paragraphs of skill output with 3 paragraphs you wrote. Sort them. Count errors.
- **Human-who-knows-you blind A/B.** Worse than Burrows' at character matching, better at catching personality misses.

Not enforced by this skill. Tools you can run when you want to validate the profile.

---

## Notes for future maintainers

- Profile is a living document. Add samples as your writing evolves: `/write-in-voice prompt-me` (interview, recommended for low friction) or `/write-in-voice add <register>` (paste an existing piece). Re-extract (`/write-in-voice extract`) every few months.
- If the corpus loses register coverage (you stop writing in one register), drafts in that register will degrade. Prune outdated samples too.
- Negative lists are owned by `/humanize-text`. Do not duplicate them here -- reference them.
- Storage is the corpus directory named in the settings, `$CORPUS/{profile.md, samples/}`, read and written there directly. Keep it in a private repo: the samples are the user's own writing.
- Research base behind this design: Voiceprint pattern (sample-by-register), Nielsen Norman tone-of-voice four dimensions, register-analysis prompting (arxiv 2505.00679), EMNLP 2025 "Catch Me If You Can" (arxiv 2509.14543). Implicit informal styles are the hardest LLM target; sample density matters most for casual register.
- Expect a "good draft you'd still need to edit," not a perfect ghostwriter. Published ceiling on style replication for informal registers is materially below the marketing.
