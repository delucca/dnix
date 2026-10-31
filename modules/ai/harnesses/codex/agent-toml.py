#!/usr/bin/env python3
"""Render Codex agent TOMLs from the markdown agent definitions.

Usage: agent-toml.py OUTDIR AGENT.md...

Each agent file is YAML frontmatter between --- fences and a markdown body.
Codex wants name, description and developer_instructions (the body); the
other frontmatter keys are Claude's and have no Codex equivalent.
"""
import pathlib
import sys

import tomli_w
import yaml

out = pathlib.Path(sys.argv[1])
for src in map(pathlib.Path, sys.argv[2:]):
    text = src.read_text(encoding="utf-8")
    parts = text.split("\n---\n", 1)
    if not text.startswith("---\n") or len(parts) < 2:
        sys.exit(f"{src}: no ---fenced YAML frontmatter")
    front = yaml.safe_load(parts[0][4:])
    body = parts[1].strip()
    doc = {
        "name": front["name"],
        "description": front["description"].strip(),
        "developer_instructions": body,
    }
    (out / f"{front['name']}.toml").write_text(
        f"# Rendered by dnix from modules/ai/{src.parent.parent.name}/agents/{src.name} -- edit the source, then switch.\n"
        + tomli_w.dumps(doc),
        encoding="utf-8",
    )
