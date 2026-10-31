# Diagram design principles (engine-agnostic)

How to make a diagram *good*, not merely valid. These principles apply to any
engine; the mermaid syntax that implements them is in `mermaid/`.

## The governing test: argue, don't display

A good diagram makes one relationship obvious. A bad one is a labeled bag of
boxes. Two checks before you ship:

- **Isomorphism test** — mentally strip every text label. Does the *shape alone*
  still carry the relationship (a fan-out, a cycle, a pipeline, a hierarchy)? If
  the meaning lived entirely in the words, the structure is wrong — restructure
  so the layout does the arguing.
- **Education test** — could someone who didn't write it learn something concrete
  from it in five seconds? If it only makes sense to someone who already knows
  the system, it's documentation theater.

## Match structure to type

The relationship dictates the type. Forcing the wrong type is the most common
quality failure.

| The relationship is fundamentally… | Diagram family |
|---|---|
| One thing leads to another; branching logic | Flow |
| Ordered exchange between participants over time | Sequence / interaction |
| A thing that can be in one of several states | State machine |
| Entities that relate to each other (data) | Entity-relationship |
| Whole/part, parent/child, nesting | Hierarchy / tree / class |
| Events along a time axis | Timeline / schedule |
| Items positioned on two axes | Quadrant / scatter |
| Quantity flowing and splitting | Sankey / flow-volume |

When two fit, pick the one whose **default layout tells the story without
fighting it**: don't bend a flowchart into a timeline, or a sequence into a tree.

## Layout & direction

- **`LR` (left→right)** for wide structures: pipelines, dependency graphs,
  request/response chains. Matches the shape of a screen and reads like a
  sentence.
- **`TD`/`TB` (top→down)** for sequential decision flows and shallow trees where
  "down" means "next".
- Tiny edits can reshuffle an entire auto-layout (the default engine is not
  positionally stable). If a layout is fighting you, change direction or split
  before hand-tuning.

## Naming & labeling

- **Stable, descriptive IDs**: `paymentGateway`, not `A`. The ID list *is* the
  edge list — meaningful IDs make the source readable and reduce miswiring.
- **Separate ID from display label**: keep the human text in the label so you can
  rename freely without touching every edge.
- **Short labels.** A node is a noun phrase, an edge is a verb or condition. If a
  label needs a sentence, the diagram is at the wrong altitude.

## Managing complexity

- **Group** related nodes (subgraphs / clusters) by subsystem, ownership
  boundary, or lifecycle phase. Grouping is the primary tool against edge
  spaghetti.
- **Cap node count** around 15. Beyond that, comprehension falls off a cliff and
  the render shrinks to unreadable. Split into a high-level diagram plus
  drill-downs.
- **Avoid the 5-edge hub.** A single node with many edges in and out is a sign
  the diagram is doing two jobs — factor it.

## Styling

- Style to encode **meaning**, not decoration. Define semantic roles
  (e.g. `success`, `error`, `external`, `primary`) and apply them consistently.
- **2–3 colors max.** A rainbow diagram signals nothing because everything is
  emphasized.
- Always set background **and** text color together so contrast survives. Don't
  rely on color alone to carry meaning (colorblind readers, grayscale prints).
- Prefer the renderer's native theme on shared platforms (e.g. GitHub) so the
  diagram adapts to light/dark mode instead of clashing with it.

## Accessibility

- Provide a title and description (`accTitle`/`accDescr` in mermaid).
- Always add a **one-line prose summary outside the diagram**. Most renderers
  expose nodes to screen readers but *not the edges between them*, so the
  connections — the whole point — are invisible without prose.
- Don't encode the only copy of any information in color or position alone.

## When to split vs. zoom

- One concept per diagram. If you're tempted to add a legend explaining three
  unrelated subsystems, that's three diagrams.
- A good set is often: one **context** diagram (how the pieces relate) + one
  **detail** diagram per piece that needs it.
