# Mermaid syntax safety — defensive rules

The #1 failure is code that doesn't parse. These rules, followed by default,
prevent almost all of it. Each is shown as a failing→fixed pair.

## 1. Reserved words as node IDs

`end`, `graph`, `subgraph`, `style`, `class`, `classDef`, `click`, `direction`,
`linkStyle` are grammar keywords (case-sensitive). As a bare ID they break the
parser — often silently shifting everything after them. `end` is the most common.

```
# FAIL
flowchart LR
    a --> end --> b
# FIX (uppercase, or safe ID + quoted label)
flowchart LR
    a --> END --> b
    a --> endNode["end"] --> b
```

Default rule: never name a node `end`; suffix it (`endNode`, `final`) and put the
word in the quoted label.

## 2. IDs starting with `o` or `x`

`a --o b` and `a --x b` are edge markers (circle/cross ends). An ID beginning
with `o`/`x` right after an edge gets misread.

```
# FAIL  (parsed as "a" --o "key...")
flowchart LR
    a-->okStep
# FIX
flowchart LR
    a --> okStep        %% space around --> disambiguates
    a --> OkStep        %% or capitalize the ID
```

## 3. Special characters in labels → quote everything

Any label containing `(` `)` `[` `]` `{` `}` `<` `>` `:` `;` `&` `"` `#` (or
punctuation-with-spaces) must be wrapped in double quotes. Quoting turns the
label into an opaque string so shape delimiters stop being parsed.

```
# FAIL
flowchart LR
    a[Check status (retry?)]
    b[Status: OK]
# FIX
flowchart LR
    a["Check status (retry?)"]
    b["Status: OK"]
```

Default rule: **when in doubt, quote the label.** Quoting never hurts.

## 4. Escaping inside labels — entities, not backslashes

Mermaid has no backslash escape. To put a special char *inside* a quoted label,
use an HTML entity (the `#NNN;` / `#name;` shorthand, no leading `&`):

| Char | Entity |
|---|---|
| `"` | `#quot;` |
| `#` | `#35;` |
| `&` | `#amp;` |
| `<` | `#lt;` |
| `>` | `#gt;` |
| `;` | `#59;` |

```
# FAIL  (backslash doesn't escape; literal newline breaks)
a["Say \"hi\""]
b["line1
line2"]
# FIX
a["Say #quot;hi#quot;"]
b["line1<br/>line2"]
```

Line breaks inside labels: `<br/>` (with slash). Never a literal newline or `\n`.

## 5. Node ID character set

IDs are `[A-Za-z0-9_]` only — no dots, slashes, hyphens, or spaces. Put the real
text in the label.

```
# FAIL
com.example.Service --> b
# FIX
svc["com.example.Service"] --> b
```

## 6. Comments

`%%` only (double percent), on its own line. A single `%` does nothing useful,
and `%%` mid-line will truncate that line. Never put `%%` inside label text.

## 7. Per-type escaping differences

Escaping is **not uniform** across diagram types. Quick map:

| Type | Quoted labels? | Entities? | Notes |
|---|---|---|---|
| flowchart | yes `"..."` | yes | also `<br/>`, v10+ backtick markdown strings |
| stateDiagram-v2 | yes (`state "L" as id`) | partial | |
| sequenceDiagram | participant names: no (use `as`); message body: free after first `:` | no | colon in name breaks |
| classDiagram | no quoting of members | use `~T~` for generics | `<T>` breaks |
| erDiagram | names alphanumeric+`_` only | no | no spaces in entity names |
| gantt | no | no | `:` forbidden in task/section names |
| mindmap | **no quoting** | no | plain words only; avoid `()[]{}` |
| pie | yes for slice labels | — | values must be positive |

```
# class generics — FAIL then FIX
class Box { List<String> items }
class Box { List~String~ items }

# gantt — FAIL then FIX
Deploy: app : done, 2026-01-01, 1d
Deploy app : done, 2026-01-01, 1d
```

## 8. Front-matter & init

- YAML front-matter config goes in a `---` block as the **first lines**, above the
  diagram keyword. Keys are case-sensitive; a typo fails silently.
- The `%%{init: {...}}%%` directive must contain valid JSON. **Avoid using it to
  set a theme on GitHub** — it overrides GitHub's dark-mode and usually produces
  low-contrast output. Prefer the platform's native theme.

## 9. Version / target compatibility

Newer syntax fails on lagging renderers. Treat these as latest-only and avoid
when the target is GitHub/GitLab/Obsidian/Notion or unknown:

- `@{ shape: ... }` semantic flowchart nodes (v11.3+)
- `layout: elk` and `look: handDrawn` (v11)
- beta diagram types: `architecture-beta`, `block-beta`, `packet-beta`, and
  newer ones (`venn`, `ishikawa`, `radar`, `treemap`, …)

GitHub renders ~v11.4. When unsure of the target, **use the conservative subset**
(see `diagram-types.md` "broadly supported").

## 10. Pre-flight checklist (run mentally before validating)

1. First line is a valid diagram keyword.
2. No bare reserved-word IDs; no IDs starting with `o`/`x` after an edge.
3. Every label with a special char is double-quoted.
4. Embedded specials use `#...;` entities; line breaks use `<br/>`.
5. IDs are `[A-Za-z0-9_]` only.
6. Type-specific rules honored (`~T~` generics, no `:` in gantt names, plain
   mindmap text).
7. No latest-only syntax if the target can't render it.
8. `accTitle`/`accDescr` present; prose summary will accompany the block.
