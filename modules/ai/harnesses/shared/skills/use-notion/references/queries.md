# Filters, sorts, and property shapes

Load when building a `query --filter` / `--sorts`, or a `create --properties` /
`set-props --properties` payload. Everything here is JSON passed verbatim to the
API, so a shape error surfaces as a Notion 400, not a script error.

## Where rows live (the 2025-09-03 model)

A **database** is a container. Its **data sources** hold the schema and the rows.
One database can carry several. So:

```bash
uv run $SCRIPT db <database-url>          # -> prints each data source id
uv run $SCRIPT query <data-source-id> ... # -> the rows
```

Passing a database id to `query` fails. Passing a data source id to `db` fails.
Any recipe found online that does `POST /v1/databases/:id/query` predates this
split and its ids are wrong.

## Filters

A filter is one condition, or a `and`/`or` array of them (nestable two levels):

```json
{"property": "Status", "status": {"equals": "In progress"}}
```

```json
{"and": [
  {"property": "Status", "status": {"does_not_equal": "Done"}},
  {"property": "Due",    "date":   {"on_or_before": "2026-09-01"}}
]}
```

Condition keys by property type:

| Type | Key | Common conditions |
|---|---|---|
| title, rich_text, url, email, phone_number | `rich_text` | `equals`, `contains`, `starts_with`, `is_empty` |
| number | `number` | `equals`, `greater_than`, `less_than_or_equal_to` |
| checkbox | `checkbox` | `equals` (true/false) |
| select | `select` | `equals`, `does_not_equal`, `is_empty` |
| status | `status` | `equals`, `does_not_equal` |
| multi_select | `multi_select` | `contains`, `does_not_contain` |
| date, created_time, last_edited_time | `date` | `equals`, `before`, `after`, `on_or_before`, `past_week`, `next_month` |
| people, created_by, last_edited_by | `people` | `contains` (a user id) |
| relation | `relation` | `contains` (a page id), `is_empty` |
| formula | `formula` | wrap the inner type: `{"formula": {"string": {"contains": "x"}}}` |
| rollup | `rollup` | `any`, `every`, `none` wrapping an inner condition |

Timestamp filters that are not a property use `timestamp` instead:

```json
{"timestamp": "last_edited_time", "last_edited_time": {"past_week": {}}}
```

## Sorts

An array, applied in order. Property sorts and timestamp sorts differ:

```json
[{"property": "Due", "direction": "ascending"},
 {"timestamp": "last_edited_time", "direction": "descending"}]
```

## Property values for writes

`create --properties` and `set-props --properties` take a map of property NAME to
a typed value. The shapes are asymmetric with what reads return — writes are
terser:

```json
{
  "Name":     {"title":       [{"text": {"content": "Q3 retro"}}]},
  "Notes":    {"rich_text":   [{"text": {"content": "shipped late"}}]},
  "Status":   {"status":      {"name": "In progress"}},
  "Stage":    {"select":      {"name": "Draft"}},
  "Tags":     {"multi_select":[{"name": "eng"}, {"name": "infra"}]},
  "Estimate": {"number":      3},
  "Done":     {"checkbox":    false},
  "Due":      {"date":        {"start": "2026-09-01", "end": null}},
  "Owner":    {"people":      [{"id": "<user-uuid>"}]},
  "Blocks":   {"relation":    [{"id": "<page-uuid>"}]},
  "Link":     {"url":         "https://example.com"}
}
```

Rules that bite:

- **Property names are case- and space-sensitive** and must already exist on the
  data source. Creating a property means `API-update-a-data-source`, not a page write.
- **`select` and `status` values must already exist** in the schema for `status`;
  `select` will create a new option, `status` will not.
- **The title property is not always called `Title`.** Run
  `raw API-retrieve-a-data-source --args '{"data_source_id": "..."}'` to read the
  real names, and pass `--title-property` on `create`.
- **Formula and rollup properties are read-only** — writing them 400s.

## Notion-flavored Markdown (`read` / `update`)

The markdown tools speak an extended dialect. Standard headings, lists, tables,
code fences, and links round-trip. Beyond that:

- Child pages and databases appear as link references. `update` will not delete
  them unless `--allow-deleting` is passed.
- Callouts, toggles, and columns survive a `read` -> `update` round trip; hand-written
  markdown for them is best copied from a `read` of an existing page.
- Meeting-note transcripts are replaced by a placeholder URL unless `read
  --transcript` is passed.

For a surgical edit, prefer `update --edit OLD NEW` over rewriting the page:
`old_str` must match the markdown exactly as `read` returned it, and a
non-matching `old_str` is an error rather than a silent no-op.
