---
name: fetch-youtube-transcript
description: Fetches a YouTube transcript as plain text via yt-dlp. Use for a YouTube URL, or when fetch-transcript dispatches. NOT for non-YouTube sources or downloading media.
allowed-tools: Bash(bash:*), Bash(yt-dlp:*)
argument-hint: "[youtube-url] [sub-langs]"
---

# fetch-youtube-transcript — YouTube transcript via yt-dlp

Turn a YouTube URL into a clean plain-text transcript, printed to stdout with a small metadata header (title, duration, subtitle kind). One script does everything; no API keys, no browser.

## When NOT to use this skill

Not for non-YouTube sources — use `fetch-transcript`, which routes by source type. Not for downloading video or audio files. Not for summarizing the video — fetch first, then summarize in conversation.

**Dependency:** `yt-dlp` (from dnix's `modules/ai`, which ships it beside `ffmpeg-full`) and `jq`. The script checks both and fails with the install command if missing.

## Usage

```bash
bash {baseDir}/scripts/fetch.sh "<youtube-url>"
bash {baseDir}/scripts/fetch.sh "<youtube-url>" "en.*"   # restrict subtitle languages
```

Output format:

```
TITLE: Vectors | Chapter 1, Essence of linear algebra
DURATION: 9:52
SUBTITLES: manual (en)
---
<one caption line per row>
```

## Steps

1. Take the URL from `$ARGUMENTS` or the conversation. Pass it quoted — YouTube URLs contain `&`.
2. Run the script. It prefers the creator's manual subtitles (correct punctuation and technical terms) and only falls back to auto-captions when no manual subs exist — the `SUBTITLES:` header says which one you got.
3. Relay the transcript to whatever asked for it. When the caller is another skill, keep the transcript in context as working material — do not write it to disk unless explicitly asked.

If the transcript came from auto-captions, mention that to the caller: auto-captions garble formulas and proper nouns, so grading or quoting from them deserves a grain of salt.

## Troubleshooting

- **`ERROR: no subtitles available`** — the video has neither manual nor auto subs in the requested languages. Retry once with the second argument set to `"all"`; if that also fails, report it so the caller can fall back to asking the user for the transcript.
- **`yt-dlp not found`** — install it, and keep it current: a stale yt-dlp is a broken tool against YouTube.
- **Age-restricted / members-only video** — yt-dlp fails without cookies. Report the failure; do not attempt cookie extraction.
- **Playlist URL given** — the script passes `--no-playlist`, so a `watch?v=…&list=…` URL fetches only that one video. To transcribe several episodes, call the script once per video URL.

## Hard prohibitions

- Never download video or audio — `--skip-download` stays. The skill exists for text.
- Never bulk-fetch a whole playlist in one invocation — each video is one explicit call, so the caller controls scope and cost.
