
---

## LIBRARY DOCS

Before using ANY library, pull current docs through the `/use-context7` skill: `use-context7 resolve <library>` for the ID, then `use-context7 query <id> "<question>"` (or the one-shot `use-context7 lookup <library> "<question>"`). Follow the latest patterns it returns.

Query latest via the skills: `/use-context7` → `/use-bright-data` → `web_search`

The researcher agents and `research` reach the web and indexed sources through the gateway skills: `/use-bright-data` for search and scraping, `/use-nia` for indexed repos, docs and papers, `/use-context7` for library docs. Fall back to the built-in web tools only when a gateway fails.
