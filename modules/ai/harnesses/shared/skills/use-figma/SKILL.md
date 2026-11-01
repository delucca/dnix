---
name: use-figma
description: Reads Figma Design files and FigJam boards through the Figma desktop app's MCP server, read-only. Use for a figma.com link, "look at my Figma", "read this FigJam board", the current selection. NOT for editing Figma.
allowed-tools: Bash(uv run *), Read
argument-hint: "[status|tools|describe|get] [tool or alias] [figma url]"
---

# use-figma -- read Figma and FigJam from the desktop app

Read a design, a board or the current selection out of the Figma desktop app.
The script speaks MCP to the Dev Mode server the app serves on
`127.0.0.1:3845`, runs one read, prints it and exits, so no MCP server is
registered and no tool schema sits in context.

The skill is read-only by design. The script refuses every tool outside its
read list, which keeps out the Code Connect writes the desktop server also
serves. Figma's write tools (`use_figma`, `generate_diagram`, `create_new_file`)
live only on the remote server, which this skill does not use.

## Requirements

- The Figma desktop app, signed in with a **Dev or Full seat on a paid plan**:
  the desktop server is not offered on other seats.
- The desktop server switched on: in a Design file, press Cmd+/ and run the
  Quick Action **Enable desktop MCP server**. The Dev Mode panel only offers
  to auto-install MCP into a client; skip that, dnix strips it on switch.
- `uv` on PATH. The first run fetches the pinned `mcp` SDK.

## Usage

```bash
SCRIPT={baseDir}/scripts/figma.py
uv run $SCRIPT status                         # server up? which tools?
uv run $SCRIPT get <tool|alias> [figma-url] [--args '{...}']
uv run $SCRIPT describe <tool|alias>          # input schema, before unusual args
```

Every tool reads the **frontmost file** in the app; the desktop server takes
no file key and cannot open a file. Without a URL a tool reads the current
selection, or the whole page when nothing is selected. With a URL the script
takes only its `node-id`, so a link to a file that is not in front reads the
wrong node or fails: ask the user to bring that file's tab forward first.

FigJam files accept only `board` and `shot`; the other tools are for Design.

| Alias | Tool | Reads | Use for |
|---|---|---|---|
| `board` | `get_figjam` | FigJam | Stickies, shapes, connectors and sections as XML, plus screenshots |
| `outline` | `get_metadata` | Design | A cheap XML outline: layer ids, names, types, sizes |
| `context` | `get_design_context` | Design, Make | Layout, styles and reference code (React + Tailwind by default) |
| `shot` | `get_screenshot` | Design, FigJam, Slides | An image of the node |
| `vars` | `get_variable_defs` | Design | Variables and styles a node uses |
| `motion` | `get_motion_context` | Design | Keyframe animation data |
| `code-connect` | `get_code_connect_map` | Design | Code Connect mappings of selected instances |

`status` lists what this app version serves; tools in the read list that it
does not serve (the shader readers, on some versions) fail with a clear error.

## Workflow

1. **Run `status` first.** It tells you whether the server is up and which
   tools this app version serves, so a failed read is never the first sign.
2. **Pick the reader by file type.** A `figma.com/board/...` URL is FigJam:
   use `board`. A `figma.com/design/...` URL is a design: go to step 3.
3. **Outline before context on anything large.** `get_design_context` on a
   whole page returns a payload too large to use. Run
   `outline` on the page or frame, pick the node ids that matter, then run
   `context` on each with `--args '{"nodeId":"12:34"}'`.
4. **Read images from disk.** `shot` and `board` write each image to
   `~/.cache/figma-cm/` and print the path. Open it with `Read` to see it.
5. **Large output spills.** Results over 4 KB are saved under the same folder
   with a 1500-char preview printed. Read the file for the rest.

On a big board, ask the user to select one section and run `board` with no URL:
the selection keeps the XML to the part they care about.

## Examples

```bash
uv run $SCRIPT get board "https://www.figma.com/board/AbC123/Retro?node-id=0-1"
uv run $SCRIPT get outline "https://www.figma.com/design/AbC123/App?node-id=42-7"
uv run $SCRIPT get context --args '{"nodeId":"42:9","clientFrameworks":"vue"}'
uv run $SCRIPT get shot                       # whatever is selected right now
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Cannot reach the Figma desktop MCP server` | App closed, or the server is off. In a Design file, Cmd+/ then **Enable desktop MCP server**. |
| No such Quick Action | The seat is View or Collab, or the plan is free. The desktop server needs a paid Dev or Full seat. |
| `FigJam files may only use the following tools` | A Design tool was run on a board. Use `board` or `shot`. |
| A Specs doc on a board comes back as empty hidden `spec-block`s | The desktop server cannot read Specs text, and a `shot` shows only the collapsed icon. Ask the user to paste it. |
| A trailing line recommending the remote server | Figma appends it to every result. Ignore it. |
| An empty or "select a node" result | No URL was passed and nothing is selected. Ask the user to select a node, or pass the URL. |
| Result is about the wrong file | Tools act on the frontmost file. Ask the user to bring the right tab forward. |
| `is not a read tool here` | The tool writes, or is unknown. This skill only reads. |

## Hard prohibitions

- Never call a tool outside the script's read list, and never edit the list to
  add a writer: the user asked for read-only Figma access, and writes land on
  a canvas their team shares.
- Never register the Figma MCP server in `~/.claude.json` or another harness
  config. dnix empties `mcpServers` on every switch; the no-MCP rule is why
  this skill is a script.
- Never register a client with Figma's remote server, in particular under
  another client's name such as "Claude Code". The remote server limits
  registration to approved clients, and borrowing a name to get past that is
  a workaround outside this read-only skill.
