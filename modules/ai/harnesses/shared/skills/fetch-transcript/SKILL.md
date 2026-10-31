---
name: fetch-transcript
description: Detects a resource's source type (YouTube, article, PDF, file) and dispatches to the right fetcher. Use for "get the text of this link". NOT for summarizing or scraping.
allowed-tools: Skill, WebFetch, Read, Glob
argument-hint: "[url | caminho do arquivo]"
---

# fetch-transcript — source-type router for resource content

Resolve "I need the text of this resource" to the right fetcher and return clean text plus a one-line provenance note — this skill decides *how to fetch*, never *what to do with the content*.

## When NOT to use this skill

Not to summarize or analyze the content — fetch first, then work with it in conversation. Not to download media. Not to scrape arbitrary structured data from sites — use an installed scraping skill directly for that, if one is listed.

## Routing table

| Source | Detect by | Fetcher |
|---|---|---|
| YouTube video | `youtube.com` / `youtu.be` URL | Skill `fetch-youtube-transcript` |
| PDF | URL or path ending in `.pdf` | Skill `use-pdf-reader` |
| Local text file | path that exists on disk (`.md`, `.txt`, …) | Read |
| Web article / blog post | any other `http(s)` URL | WebFetch first; if blocked, paywalled, or the result is empty/navigation-only → an installed scraping skill, if one is listed |
| Login-walled platform (Coursera, Udemy, …) | fetch returns a login page, or the domain is a known course platform | ask the user to paste |

Adding a future fetcher (podcast, EPUB, …) = one row here plus its skill — keep this table as the single routing source.

## Steps

1. **Identify the resource** from `$ARGUMENTS` or the conversation. No URL or path at all → ask for one (or for pasted content directly).
2. **Route** using the table and run the fetcher. One retry on a different route is fine (e.g., WebFetch came back empty → a scraping skill); more than that, fall through to step 4.
3. **Sanity-check the result**: a transcript that is shorter than a couple of paragraphs for an hour-long resource, or that reads like cookie banners and navigation, is a failed fetch — treat it as step 4, do not hand garbage to the caller.
4. **Fallback — ask the user**: "não consegui puxar a transcrição de `<recurso>` automaticamente — me cola aqui o texto/transcrição?" (YouTube's own transcript panel, the course's transcript tab, or copy-paste of the article all work). User-pasted content is treated exactly like fetched content from here on.
5. **Return** the content to the caller with a one-line provenance header: source, fetch method, and any quality caveat (e.g., auto-captions). Keep it in context as working material — never write it to disk unless explicitly asked.

## Troubleshooting

- **fetch-youtube-transcript reports no subtitles** — go straight to the paste fallback; re-scraping YouTube's page will not find captions yt-dlp could not.
- **No scraping skill available on this machine** — skip that route and use the paste fallback.
- **Huge resource (multi-hour video, whole book)** — confirm scope with the user before fetching; a checkpoint usually covers one lesson, not the entire course.

## Hard prohibitions

- Never fabricate or "reconstruct from memory" a transcript when fetching fails — downstream skills grade the user's understanding against this text, so invented content corrupts the evaluation. Fetch it or ask for it.
- Never summarize, trim, or editorialize the fetched content — the caller decides what matters.
