# Eval prompts — tldr

Real prompts that should (or should not) trigger the skill, for regression checks.

## Should trigger

1. **Happy path — after a wall of text.** In a session where the previous agent reply
   was 600+ words with headers and nested bullets: `/tldr`
   - PASS: reply opens with a one-sentence outcome; ≤120 words; no headers; any
     question from the source survives in an "On you:" line.
2. **Natural phrasing, no slash.** After a long reply: "tldr? that was way too much"
   - PASS: same digest format; subsequent replies stay terse.
3. **Inline text target.** `/tldr <400-word pasted status update>`
   - PASS: digest covers the paste, not the conversation; figures verbatim.
4. **File target with --once.** `/tldr notes/retro.md --once`
   - PASS: file is read and condensed; the NEXT unrelated reply is normal length
     (no session switch).
5. **Ask preservation.** Condense a reply whose middle contains "Should I use approach
   A or B?"
   - PASS: the A-or-B question appears in the digest. FAIL if it is dropped.

## Should NOT trigger

6. "Make this email sound less like AI" → no trigger (voice rewriting).
7. "Explain step by step why the test failed" → `explain` (depth was requested).
8. "Brief me on the Q3 migration plan" → `brief` (investigation, not compression).
