# Mermaid diagram types — catalog & templates

One entry per type: when to use it, a minimal correct template, key options, and
quirks/version notes. Load only the entry you need.

**Version reality (critical):** upstream mermaid is ~v11.15, but **GitHub renders
~v11.4**, and Obsidian/Notion lag further. Anything marked **[v11.x]** or
**[beta]** below may render as raw text on those targets. Default to the
"broadly supported" types (flowchart, sequence, class, state, ER, gantt, pie,
mindmap, timeline, journey, gitGraph, quadrantChart, C4) unless you know the
target runs latest.

All diagrams: first non-empty line is the type keyword; `%%` starts a comment;
optional YAML front-matter config goes in a `---` block *above* the keyword.

---

## flowchart (alias: graph) — broadly supported

Use when: processes, decision logic, pipelines, "how it works".

```
flowchart LR
    a["Start"] --> b{"Decision?"}
    b -->|Yes| c["Do it"]
    b -->|No| d(["Skip"])
    c --> e["End"]
    d --> e
    subgraph grp["A group"]
        direction TB
        x["x"] --> y["y"]
    end
```

- Direction: `TD`/`TB`, `BT`, `LR`, `RL`.
- Node shapes (classic, all supported): `["rect"]` `("round")` `(["stadium"])`
  `[["subroutine"]]` `[("cylinder/db")]` `(("circle"))` `{"diamond"}`
  `{{"hexagon"}}` `[/"parallelogram"/]`.
- Edges: `-->` arrow, `---` line, `-.->` dotted, `==>` thick, `--o` circle end,
  `--x` cross end, `<-->` bidirectional. Label: `a -->|text| b` or `a -- text --> b`.
- Chain: `a & b --> c & d`.
- **[v11.3]** `id@{ shape: cyl, label: "DB" }` semantic shapes — newer renderers
  only; avoid for GitHub/unknown targets.

## sequenceDiagram — broadly supported

Use when: messages/calls between actors or services over time.

```
sequenceDiagram
    autonumber
    actor U as User
    participant A as App
    participant S as Server
    U->>A: Click
    A->>+S: Request
    S-->>-A: Response
    alt ok
        A-->>U: Show result
    else error
        A-->>U: Show error
    end
    Note over A,S: handshake
```

- Arrows: `->>` solid+head, `-->>` dashed+head, `->` solid no head, `-x`/`--x`
  cross, `-)` async. Activation: `+`/`-` on the arrow, or `activate`/`deactivate`.
- Blocks: `loop`, `alt/else`, `opt`, `par/and`, `critical/option`, `break`,
  `rect`.
- Reserved block words can't be participant names: `loop alt else opt par and
  critical break rect end note over activate deactivate`.
- A `:` after the arrow separates actor from message; colons *inside* the message
  body are fine. Avoid `:` in participant names — use `as`.

## stateDiagram-v2 — broadly supported

Use when: lifecycle, finite states & transitions. (Prefer `-v2`.)

```
stateDiagram-v2
    direction LR
    [*] --> Idle
    Idle --> Working : start
    Working --> Done : finish
    Working --> Error : fail
    Error --> Idle : reset
    Done --> [*]
    state Working {
        [*] --> Step1
        Step1 --> Step2
    }
```

- `[*]` is start/end. Composite states nest with `state Name { ... }`.
- Special: `state c <<choice>>`, `<<fork>>`, `<<join>>`. Parallel regions inside
  a composite state are split by `--`.
- Long label: `state "Human label" as s1`.

## erDiagram — broadly supported

Use when: data models, schema, entity relationships.

```
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ LINE_ITEM : contains
    CUSTOMER {
        int id PK
        string email UK
        string name
    }
    ORDER {
        int id PK
        int customer_id FK
    }
```

- Cardinality (left+right): `|o` zero-or-one, `||` exactly-one, `}o`
  zero-or-many, `}|` one-or-many. Line: `--` identifying, `..` non-identifying.
- Attribute keys: `PK`, `FK`, `UK`. Entity/attr names: alphanumeric + `_` only.

## classDiagram — broadly supported

Use when: OOP structure, classes, interfaces.

```
classDiagram
    direction TB
    class Animal {
        +String name
        +int age
        +speak() String
        +move()*
    }
    class Dog
    Animal <|-- Dog : inherits
    Dog "1" --> "*" Toy : plays with
    note for Dog "man's best friend"
```

- Visibility: `+` public, `-` private, `#` protected, `~` package. Classifier:
  `*` abstract, `$` static.
- Relations: `<|--` inheritance, `*--` composition, `o--` aggregation, `-->`
  association, `..>` dependency, `..|>` realization.
- **Generics use tildes**, not angle brackets: `List~String~`. Stereotypes:
  `<<interface>>` `<<enumeration>>`.

## mindmap — broadly supported

Use when: hierarchy of ideas, brainstorm, tree.

```
mindmap
  root((Central idea))
    Topic A
      Detail 1
      Detail 2
    Topic B
      ::icon(fa fa-star)
      Sub B
```

- **Hierarchy is indentation** — be consistent (2 spaces), no tabs mixed in.
- Shapes via suffix: `[sq]` `(round)` `((circle))` `)cloud(` `{{hex}}`.
- **No double-quote escaping** here — use plain words; avoid `()[]{}` inside text.

## timeline — broadly supported

Use when: chronological events, history, roadmap.

```
timeline
    title Product roadmap
    section 2025
        Q1 : Feature A : Bug fixes
        Q2 : Feature B
    section 2026
        Q1 : v2 launch
```

- Multiple events per period: repeat `: event` or stack on following lines.

## gantt — broadly supported

Use when: schedules — tasks with dates & dependencies.

```
gantt
    title Project
    dateFormat YYYY-MM-DD
    excludes weekends
    section Build
        Design  :done, des1, 2026-01-01, 5d
        Backend :active, dev1, after des1, 10d
        Ship    :milestone, m1, after dev1, 0d
```

- Tags: `done`, `active`, `crit`, `milestone`. Durations: `d w h m`. Relative:
  `after taskId`.
- **Task and section names cannot contain `:`** — it's the field separator.

## pie — broadly supported

Use when: simple part-of-whole. (Use sparingly — weak at comparison.)

```
pie showData title Share
    "Dogs" : 45
    "Cats" : 30
    "Birds" : 25
```

## journey — broadly supported

Use when: user-experience steps with satisfaction scores (1–5).

```
journey
    title Shopping
    section Browse
        Search : 5: Customer
        Compare : 3: Customer
    section Buy
        Checkout : 4: Customer, Support
```

## gitGraph — broadly supported

Use when: branch/merge/release history.

```
gitGraph
    commit id: "init"
    branch develop
    commit
    checkout main
    merge develop tag: "v1.0"
```

- Commit `type:` `NORMAL` | `HIGHLIGHT` | `REVERSE`. Orientation `gitGraph LR:`.

## quadrantChart — broadly supported (v10.3+)

Use when: 2×2 positioning (effort/impact, reach/value).

```
quadrantChart
    title Prioritization
    x-axis Low Effort --> High Effort
    y-axis Low Impact --> High Impact
    quadrant-1 Do first
    quadrant-2 Schedule
    quadrant-3 Drop
    quadrant-4 Delegate
    Feature A: [0.3, 0.8]
    Feature B: [0.6, 0.2]
```

- Points are `[x, y]` in 0–1. Quadrant numbering: 1=top-right, ccw.

## C4 (C4Context / C4Container / C4Component / C4Dynamic / C4Deployment) — v10.7+

Use when: software architecture at C4 abstraction levels.

```
C4Context
    title System context
    Person(user, "User", "A customer")
    System(app, "Web App", "Main system")
    System_Ext(pay, "Payments", "3rd party")
    Rel(user, app, "Uses", "HTTPS")
    Rel(app, pay, "Charges via")
```

- Suffixes: `_Ext` external, `Db`, `Queue`. Layout is finicky — keep it small.

---

## Situational / newer — check target support first

- **sankey-beta** [beta] — flow volumes. CSV body: `source,target,value`.
- **xychart-beta** [v10.2] — bar/line charts: `x-axis [..]`, `y-axis "L" 0 --> 100`,
  `bar [..]`, `line [..]`.
- **block-beta** [v11] — block/component grids: `columns 3` then nodes; nested
  `block:id ... end`.
- **architecture-beta** [v11] — cloud/service topology: `group g(cloud)[Cloud]`,
  `service db(database)[DB] in g`, edges `a:R --> L:b`.
- **requirementDiagram** — systems-engineering requirement tracing.
- **packet-beta** [v11.7] — network packet layouts.
- **mindmap icons** need Font Awesome available in the renderer.

For any of these, prefer them only when the user's render target runs current
mermaid (mermaid.live, Mermaid Chart, a docs site you control, or `mmdc`).
