"""Render Codex agent TOMLs from the markdown agent definitions.

Usage: codex-agent-toml OUTDIR AGENT.md...

Each agent file is YAML frontmatter between --- fences and a markdown body.
Codex wants name, description and developer_instructions (the body); the
other frontmatter keys are Claude's and have no Codex equivalent, so a Claude
tools list does not restrict the agent in Codex.

A source that cannot be rendered is reported on stderr as one line, skipped, and
makes the exit status 1; the others are still written.
"""
import pathlib
import sys

import tomli_w
import yaml


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
    doc = {
        "name": name,
        "description": description.strip(),
        "developer_instructions": parts[1].strip(),
    }
    (out / f"{name}.toml").write_text(
        f"# Rendered for Codex from {src}; edit that file.\n" + tomli_w.dumps(doc),
        encoding="utf-8",
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
            print(f"codex-agent-toml: {src}: {reason}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
