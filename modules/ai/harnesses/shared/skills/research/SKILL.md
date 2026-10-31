---
name: research
description: Fans out web, academic, code and docs research agents into a report. Use for "research", "investigate X". NOT for a lookup, coordination (orchestrate), or a plan (tech-lead).
argument-hint: "[topic] [--depth quick|deep|exhaustive]"
allowed-tools:
  - Agent
  - AskUserQuestion
  - Bash(wc *)
  - Read
  - Write
  - Skill(bilbo:recall)
  - Skill(bilbo:note)
  - Skill(bilbo:ingest)
---

# Research

Decompose a topic into subtopics, fan out specialized research agents in parallel, and synthesize their findings into a unified report.

## When NOT to use this skill

- Simple factual questions answerable from context.
- Code implementation tasks.
- Single-source lookups - use `bilbo:recall` instead.

## Phase 1 — Understand the request

### 1a. Parse arguments

Extract from `$ARGUMENTS`:
- **topic**: The research subject (required)
- **depth**: `quick`, `deep`, or `exhaustive` (default: `deep`)

### 1b. Assess clarity

If the topic is specific enough to decompose (e.g., "CRDT implementations for collaborative editing"), proceed to Phase 2.

If the topic is too broad or vague (e.g., "distributed systems"), ask 2-3 clarifying questions:
- What specifically do you want to learn?
- What do you already know that I can skip?
- Is there a decision this research should inform?

Keep the interview under 3 questions. Extract scope, not precision — the subtopic decomposition handles precision.

## Phase 2 — Decompose into subtopics

Break the topic into subtopics based on depth:

| Depth | Subtopics | Agents per subtopic | Expected duration |
|---|---|---|---|
| quick | 2-3 | 1-2 | 2-5 min |
| deep | 3-5 | 2-3 | 5-15 min |
| exhaustive | 5-8 | 3-4 | 15-30 min |

For each subtopic, decide which agent types are relevant:

| Agent | Use when the subtopic involves |
|---|---|
| web-researcher | General knowledge, current events, opinions, comparisons, tutorials |
| academic-researcher | Theory, algorithms, formal methods, peer-reviewed evidence |
| code-researcher | Libraries, frameworks, implementation patterns, APIs, code examples |
| docs-researcher | Internal specs, PRDs, design docs, past decisions, conventions |

Not every subtopic needs every agent type. A subtopic about "React Server Components performance" needs web-researcher and code-researcher, but probably not academic-researcher.

### 2a. Present the plan

Show the user the subtopic decomposition before spawning agents:

```
## Research plan: {topic}
Depth: {depth}

### Subtopics
1. {subtopic 1} → agents: {web, code}
2. {subtopic 2} → agents: {web, academic}
3. {subtopic 3} → agents: {code, docs}
...

Estimated agents: {total count}
```

Wait for user approval. The user may adjust subtopics, add/remove agents, or change depth.

## Phase 3 — Fan out agents

Spawn all agents in parallel using the `Agent` tool. Each agent call must include:

1. **subagent_type**: The agent name (e.g., `web-researcher`)
2. **A self-contained prompt** with:
   - The subtopic and research question
   - The depth level
   - Any context from Phase 1 that prevents redundant searching
   - The expected output format (the agent knows its own format, but reinforcing it reduces drift)

Spawn agents for the same subtopic in a single message to maximize parallelism. Spawn agents for independent subtopics in the same message as well.

Example agent spawn:

```
Agent({
  subagent_type: "web-researcher",
  description: "Research CRDT conflict resolution",
  prompt: "Subtopic: CRDT conflict resolution strategies. Question: What are the tradeoffs between operation-based and state-based CRDTs for real-time collaborative editing? Depth: deep. Context: We're evaluating CRDTs for a collaborative text editor. We already know Yjs and Automerge exist but need deeper comparison."
})
```

## Phase 4 — Synthesize findings

After all agents return, synthesize their findings into a unified report. This is the most important phase — raw agent outputs are useful but disconnected. The synthesis adds value by:

1. **Cross-referencing**: Where do different agent findings agree or conflict?
2. **Filling gaps**: Did one agent's findings answer another agent's open questions?
3. **Prioritizing**: What are the most important findings for the user's original question?
4. **Identifying remaining gaps**: What couldn't be answered?

### 4a. Synthesis structure

Adapt the output format to the depth level:

**Quick depth** — conversational summary:
- 3-5 key findings in prose
- Source links inline
- Open questions if any

**Deep depth** — structured report:

```
## Research: {topic}

### Key findings
- {Finding 1} [confidence: high/medium/low]
  - Evidence: {summary from agents}
- {Finding 2} ...

### Detailed analysis
#### {Subtopic 1}
{Synthesized findings across agents, not per-agent dumps}

#### {Subtopic 2}
...

### Contradictions and debates
- {Where sources disagree, with evidence from each side}

### Open questions
- {What remains unanswered}

### Sources
{Deduplicated, ranked by relevance}
```

**Exhaustive depth** — full report with the above plus:
- Methodology landscape (how different approaches compare)
- Timeline/history (how the field evolved)
- Recommendations (if the research was decision-oriented)

### 4b. Present findings

Show the synthesized report to the user. Then offer next steps:

1. **Go deeper**: "Want me to investigate any subtopic further?"
2. **Save as a note**: "File this as a `research` note?"
3. **Ingest the sources**: "Ingest the key sources into bilbo's library for future use?"

If the user wants to save it as a note, route to `bilbo:note` with `--kind research`. If they want to ingest sources, route to the `bilbo:ingest` skill (one call per source URL).

## Phase 5 — Follow-up (optional)

If the user asks to go deeper on a specific subtopic:

1. Treat it as a new research request scoped to that subtopic.
2. Increase the effective depth by one level (quick → deep, deep → exhaustive).
3. Re-run Phases 2-4 for just that subtopic.
4. Merge the new findings with the existing report.

## Error handling

- **Agent fails to return**: Note which agent failed and what subtopic is missing. Present partial findings and offer to retry.
- **All agents for a subtopic fail**: Flag the subtopic as unresearched. Suggest alternative approaches (different keywords, different agent types).
- **User cancels mid-research**: Present whatever findings have been gathered so far.
- **Too many agents for the depth level**: Reduce to the cap. Prioritize agent types most likely to yield results for each subtopic.

## Operational constraints

- **Ground all claims in agent evidence.** Synthesized conclusions must trace back to specific agent findings. Ungrounded claims are indistinguishable from hallucination and erode trust in the research.
- **Synthesize, never relay.** Raw agent output is disconnected and repetitive. The orchestrator's value is cross-referencing and prioritizing — presenting raw dumps wastes the user's time.
- **Gate on user approval before spawning.** Each agent consumes significant tokens and time. Spawning without approval risks wasting resources on a misunderstood scope.
- **Stay within the approved plan.** Expanding scope mid-research causes runaway token costs and dilutes findings. Note interesting tangents as open questions for the user to pursue deliberately.
- **Respect depth-level caps.** Exceeding subtopic or agent counts without approval breaks the user's cost expectations.
