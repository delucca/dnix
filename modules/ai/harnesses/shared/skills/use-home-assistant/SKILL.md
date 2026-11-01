---
name: use-home-assistant
description: Controls smart home devices, lights, climate and vacuum, via Home Assistant. Use for "turn on the lights" or setting temperature. NOT for non-smart-home tasks.
allowed-tools: Bash(uv run *), Read
argument-hint: "[on|off|light|climate|play|pause|volume|vacuum|broadcast|status|raw] [args]"
---

# use-home-assistant -- on-demand smart home control via Home Assistant MCP

Control smart home devices through Home Assistant without keeping the MCP server registered permanently. The wrapper connects to the HA SSE endpoint, runs tool calls, then exits. The main agent context stays clean.

## When NOT to use this skill

- **Non-smart-home tasks** — this skill only talks to Home Assistant. For web scraping use `/use-bright-data`, for library docs use `/use-context7`.

**Why this design.** Registering the Home Assistant MCP in `~/.claude.json` injects 27 tool schemas into every conversation -- even when you never touch the smart home. This skill loads nothing until you invoke it, and cleans up immediately after.

**Setup.** `settings.url` is the Home Assistant instance's base URL, with the MCP Server integration enabled. The script reads the bearer token at use time: it runs the command `dnix.ai.secrets.readCommand` names (`op-agent read` by default) on the reference in `settings.secrets.token`, and exits with a clear error if either is missing.

**Transport.** SSE (Server-Sent Events). The script connects to the HA SSE endpoint, receives the POST URL via an `endpoint` event, then sends JSON-RPC 2.0 messages by POSTing to that URL. Responses arrive as SSE `message` events on the original connection.

## Usage

All subcommands run through one script:

```bash
SCRIPT={baseDir}/scripts/home-assistant.py
uv run $SCRIPT <subcommand> [args]
```

---

## Device control

### on -- Turn on / open / press a device

```bash
uv run $SCRIPT on "living room lamp"
uv run $SCRIPT on "garage door" --area garage
uv run $SCRIPT on "bedroom fan" --floor upstairs
```

Options:
- `--area` -- Target area (e.g. "kitchen", "bedroom")
- `--floor` -- Target floor (e.g. "upstairs", "ground floor")

### off -- Turn off / close a device

```bash
uv run $SCRIPT off "living room lamp"
uv run $SCRIPT off "all lights" --area bedroom
```

Same options as `on`.

---

## Lights

### light -- Set light brightness, color, or temperature

```bash
uv run $SCRIPT light "desk lamp" --brightness 80
uv run $SCRIPT light "living room" --color red
uv run $SCRIPT light "bedroom" --temperature 3000
uv run $SCRIPT light "kitchen" --brightness 50 --color blue
```

Options:
- `--brightness` -- 0-100 percent
- `--color` -- Color name (e.g. "red", "blue", "warm white")
- `--temperature` -- Color temperature in Kelvin (e.g. 3000, 4000)
- `--area` -- Target area

---

## Climate

### climate -- Set thermostat temperature

```bash
uv run $SCRIPT climate "thermostat" 22
uv run $SCRIPT climate "bedroom ac" 24 --area bedroom
```

Options:
- `--area` -- Target area

---

## Media

### play -- Search and play media

```bash
uv run $SCRIPT play "bohemian rhapsody"
uv run $SCRIPT play "chill vibes" --device "kitchen speaker" --type playlist
uv run $SCRIPT play "miles davis" --area "living room" --type artist
```

Options:
- `--device` -- Speaker or media player name
- `--area` -- Target area
- `--type` -- Media class: track, album, artist, playlist, genre, movie, tvshow, channel, episode

### pause / resume -- Pause or resume playback

```bash
uv run $SCRIPT pause "kitchen speaker"
uv run $SCRIPT pause --area bedroom
uv run $SCRIPT resume "living room tv"
```

Options:
- `--area` -- Target area

### next / prev -- Skip tracks

```bash
uv run $SCRIPT next "kitchen speaker"
uv run $SCRIPT prev --area bedroom
```

### volume -- Set volume level (0-100)

```bash
uv run $SCRIPT volume 50 --device "kitchen speaker"
uv run $SCRIPT volume 30 --area bedroom
```

Options:
- `--device` -- Target device name
- `--area` -- Target area

### volume-up / volume-down -- Relative volume

```bash
uv run $SCRIPT volume-up "kitchen speaker"
uv run $SCRIPT volume-down "bedroom speaker"
```

### mute / unmute -- Mute or unmute

```bash
uv run $SCRIPT mute "kitchen speaker"
uv run $SCRIPT unmute --area bedroom
```

---

## Vacuum

### vacuum -- Start, clean area, or return to base

```bash
uv run $SCRIPT vacuum start "roborock"
uv run $SCRIPT vacuum clean "roborock" --area kitchen
uv run $SCRIPT vacuum return "roborock"
```

Actions:
- `start` -- Start cleaning
- `clean` -- Clean a specific area (requires `--area`)
- `return` -- Return to base/dock

Options:
- `--area` -- Area to clean (required for `clean` action)

---

## Lists / Todos

### list-add -- Add item to a todo list

```bash
uv run $SCRIPT list-add "Shopping List" "milk"
uv run $SCRIPT list-add "Groceries" "eggs and bread"
```

### list-done -- Complete an item

```bash
uv run $SCRIPT list-done "Shopping List" "milk"
```

### list-remove -- Remove an item

```bash
uv run $SCRIPT list-remove "Shopping List" "milk"
```

### list-get -- Get items from a todo list

```bash
uv run $SCRIPT list-get "Shopping List"
uv run $SCRIPT list-get "Shopping List" --status completed
uv run $SCRIPT list-get "Groceries" --status all
```

Options:
- `--status` -- Filter: needs_action (default), completed, all

---

## Status / Context

### status -- Get live device/sensor status

```bash
uv run $SCRIPT status
uv run $SCRIPT status --name "thermostat"
uv run $SCRIPT status --area kitchen
uv run $SCRIPT status --domain light
```

Options:
- `--name` -- Specific device name
- `--area` -- Filter by area
- `--domain` -- Filter by domain (e.g. light, sensor, climate, switch)

### broadcast -- Announce message through the home

```bash
uv run $SCRIPT broadcast "Dinner is ready"
uv run $SCRIPT broadcast "Time to leave for school"
```

---

## Escape hatch

### raw -- Call any HA MCP tool directly

```bash
uv run $SCRIPT raw HassTurnOn --args '{"name": "desk lamp"}'
uv run $SCRIPT raw GetLiveContext --args '{"domain": "sensor"}'
uv run $SCRIPT raw for_all_mankind --args '{}'
```

Full tool list: `HassTurnOn`, `HassTurnOff`, `HassLightSet`, `HassClimateSetTemperature`, `HassMediaSearchAndPlay`, `HassMediaPause`, `HassMediaUnpause`, `HassMediaNext`, `HassMediaPrevious`, `HassMediaPlayerMute`, `HassMediaPlayerUnmute`, `HassSetVolume`, `HassSetVolumeRelative`, `HassSetPosition`, `HassStopMoving`, `HassVacuumStart`, `HassVacuumCleanArea`, `HassVacuumReturnToBase`, `HassBroadcast`, `HassCancelAllTimers`, `HassListAddItem`, `HassListCompleteItem`, `HassListRemoveItem`, `todo_get_items`, `GetDateTime`, `GetLiveContext`, `for_all_mankind`.

---

## Output handling

- Short results (up to 4 KB of text) print to stdout inline.
- Larger results spill to `~/.cache/ha-cm/<timestamp>-<label>.json`. The script prints the file path and the first 1500 characters.
- Read the spilled file path with the `Read` tool when you need the full content.

## Common mistakes

1. **Forgetting the device name.** Most commands need a device name or `--area`. If omitted, HA may pick the wrong device or fail.
2. **Using this for non-smart-home tasks.** This skill only talks to Home Assistant. For web scraping use `/use-bright-data`, for docs use `/use-context7`.
3. **Not reading spilled output.** When the script prints a file path, use the `Read` tool to see the full content. The inline preview is truncated.
4. **Missing URL or token.** The script exits naming what is unset (`settings.url`) or the reader's failure: the reader not on PATH, or the reference in `settings.secrets.token` not found.

## Performance notes

SSE connection setup takes 2-5 seconds. Most device commands (on, off, light, volume) complete in under 5 seconds. Media search and status queries may take longer. The tool call timeout is 15 seconds with a 15-second connection timeout.
