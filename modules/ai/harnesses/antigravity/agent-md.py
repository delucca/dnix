"""Render Antigravity CLI agent files from the markdown agent definitions.

Usage: agy-agent-md OUTDIR AGENT.md...

Each agent file is YAML frontmatter between --- fences and a markdown body.
agy reads the same shape, but silently drops an agent whose model is not one
of its tiers, refuses to start one that names a tool it does not have, and
gives one with no tools list no tools at all. So the model is mapped, each
Claude tool becomes the agy tools that do its job (Grep and Glob map to
agy's read-only search tools so a read-only agent stays read-only, and a
scoped Bash(...) is the whole shell), and an unmapped tool skips that agent.

A source that cannot be rendered is reported on stderr as one line, skipped, and
makes the exit status 1; the others are still written.
"""
import pathlib
import re
import sys

import yaml

MODELS = {"opus": "pro", "sonnet": "flash", "haiku": "flash"}
TOOLS = {
    "Bash": ["run_command"],
    "Read": ["view_file"],
    "Write": ["write_to_file"],
    "Edit": ["replace_file_content"],
    "Grep": ["grep_search"],
    "Glob": ["find_by_name"],
    "WebSearch": ["search_web"],
    "WebFetch": ["read_url_content"],
    "Skill": ["view_file"],
    "Agent": ["invoke_subagent"],
    "AskUserQuestion": ["ask_question"],
    "SendMessage": ["send_message"],
}


def render(src, out, rendered):
    text = pathlib.Path(src).read_text(encoding="utf-8")
    parts = text.split("\n---\n", 1)
    if not text.startswith("---\n") or len(parts) < 2:
        return "no ---fenced YAML frontmatter"
    try:
        front = yaml.safe_load(parts[0][4:])
    except yaml.YAMLError:
        return "frontmatter is not valid YAML"
    if not isinstance(front, dict):
        return "frontmatter is not a mapping"
    name = front.get("name")
    description = front.get("description")
    if not isinstance(name, str) or not isinstance(description, str):
        return "missing name or description"
    if not name or "/" in name or name.startswith("."):
        return f"name {name!r} is not a plain file name"
    if name in rendered:
        return f"name {name} already rendered from {rendered[name]}"
    doc = {"name": name, "description": description.strip()}
    model = front.get("model")
    if isinstance(model, str) and model in MODELS:
        doc["model"] = MODELS[model]
    claude = front.get("tools") or list(TOOLS)
    if isinstance(claude, str):
        claude = [t.strip() for t in claude.split(",")]
    if not isinstance(claude, list) or not all(isinstance(t, str) for t in claude):
        return "tools is neither a list of names nor a comma-separated string"
    tools = []
    for tool in (re.sub(r"\(.*\)$", "", t) for t in claude):
        if tool not in TOOLS:
            return f"no agy tool for {tool!r}; add it to TOOLS in agent-md.py"
        tools += [t for t in TOOLS[tool] if t not in tools]
    doc["tools"] = tools
    dump = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000)
    header = f"# Rendered for agy from {src}; edit that file."
    (out / f"{name}.md").write_text(
        f"---\n{header}\n{dump}---\n{parts[1]}", encoding="utf-8"
    )
    rendered[name] = src
    return None


def main():
    out = pathlib.Path(sys.argv[1])
    rendered = {}
    failed = False
    for src in sys.argv[2:]:
        try:
            reason = render(src, out, rendered)
        except (OSError, ValueError) as err:
            reason = str(err)
        if reason:
            print(f"agy-agent-md: {src}: {reason}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
