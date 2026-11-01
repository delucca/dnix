# Raw tool surface — `@notionhq/notion-mcp-server@2.5.1`

Load this only when a `raw` call is needed: the curated subcommands in SKILL.md
cover everything below except block-level editing and page-property items.

Verified by probing the pinned version directly (`notion.py tools` reprints it
live). The names are 1:1 with the REST API and are **not** the names in Notion's
public MCP docs — those describe the *hosted* server (`notion-search`,
`notion-fetch`, `notion-create-pages`, …), a different toolset. Do not copy tool
names out of Notion's docs site into `raw` calls.

24 tools. `[WRITE]` marks the ones `raw` refuses without `--yes`.

## Pages

| Tool | Required args | Notes |
|---|---|---|
| `API-retrieve-page-markdown` | `page_id` | `include_transcript` (bool) for meeting notes; default shows a placeholder URL |
| `API-update-page-markdown` [WRITE] | `page_id`, `type` | see modes below |
| `API-retrieve-a-page` | `page_id` | property values, not content; `filter_properties` narrows |
| `API-post-page` [WRITE] | `parent`, `properties` | body arrives as `children` block JSON, not markdown |
| `API-patch-page` [WRITE] | `page_id` | `properties`, `in_trash`, `archived`, `icon`, `cover` |
| `API-retrieve-a-page-property` | `page_id`, `property_id` | paginated; needed for long relation/rollup values |
| `API-move-page` [WRITE] | `page_id`, `parent` | parent is `{type: page_id|database_id, ...}` |

### `API-update-page-markdown` modes

`type` selects which sibling argument is read:

- `replace_content` — `{new_str, allow_deleting_content?}`. Overwrites the whole page.
- `update_content` — `{content_updates: [{old_str, new_str, replace_all_matches?}], allow_deleting_content?}`. Max **100** edits, applied in order.
- `insert_content`, `replace_content_range` — **deprecated**, do not use.

`allow_deleting_content` permits removing child pages and databases the edit
drops. Without it, such an edit fails rather than destroying a subtree.

## Blocks

| Tool | Required args | Notes |
|---|---|---|
| `API-get-block-children` | `block_id` | raw block JSON; prefer `retrieve-page-markdown` for reading |
| `API-patch-block-children` [WRITE] | `block_id`, `children` | `after` positions the insert |
| `API-retrieve-a-block` | `block_id` | |
| `API-update-a-block` [WRITE] | `block_id` | `type` payload, or `archived` |
| `API-delete-a-block` [WRITE] | `block_id` | |

## Databases and data sources

| Tool | Required args | Notes |
|---|---|---|
| `API-retrieve-a-database` | `database_id` | the container; returns the `data_sources` list |
| `API-query-data-source` | `data_source_id` | the rows live here, **not** on the database |
| `API-retrieve-a-data-source` | `data_source_id` | the schema |
| `API-update-a-data-source` [WRITE] | `data_source_id` | `title`, `description`, `properties` |
| `API-create-a-data-source` [WRITE] | `parent`, `properties` | |
| `API-list-data-source-templates` | `data_source_id` | |

## Search, users, comments

| Tool | Required args | Notes |
|---|---|---|
| `API-post-search` | — | **title match only**, no full-text, no semantic |
| `API-get-self` | — | the token's bot user; carries `bot.workspace_name` |
| `API-get-users` | — | paginated |
| `API-get-user` | `user_id` | |
| `API-retrieve-a-comment` | `block_id` | |
| `API-create-a-comment` [WRITE] | `parent`, `rich_text` | |

## Search filter and sort shapes

`API-post-search` accepts only these:

```json
{"filter": {"property": "object", "value": "page"}}
{"filter": {"property": "object", "value": "data_source"}}
{"sort":   {"direction": "descending", "timestamp": "last_edited_time"}}
```

`last_edited_time` is the only sortable timestamp and `object` the only
filterable property. `page_size` caps at 100.
