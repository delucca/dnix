#!/usr/bin/env python3
"""Fail when a profile's Codex skill catalog no longer fits its context budget.

Codex renders every installed skill into one <skills_instructions> block and
caps that block at 2% of the model's context window. Over the cap it shortens
descriptions mid-word with no ellipsis, silently, and only on Codex: the same
frontmatter keeps working on Claude Code, which never truncates.

Every profile also carries the skills of each plugin a host installs, which
Codex lists as <plugin>:<skill>, so a plugin's skills folder counts as well.

Usage: codex-skill-budget.py <profile> (<skill dir> | <plugin>=<skills folder>)...
"""

import pathlib
import re
import sys

# codex-cli 0.154.0 against a 272k-token model, read off `budget_limit` in the
# render_observability log line and cross-checked with `codex debug prompt-input`.
BUDGET = 5440
# Preamble, skill-roots table and Codex's own .system skills. Holds only while
# dnix.ai.codex.settings keeps the openai plugin skills disabled; a machine that
# installs skills outside the profile pays more, so confirm it there with
# `codex debug prompt-input`.
FIXED = 575
# Slack for a new skill and for tokeniser drift between models.
TARGET = 5000
# Worst o200k_base ratio measured, rounded down.
CHARS_PER_TOKEN = 3.70



def description(skill):
    lines = (skill / "SKILL.md").read_text().split("\n")
    if lines[0].strip() != "---":
        raise SystemExit(f"{skill}/SKILL.md: no frontmatter")
    out, reading = [], False
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("description:"):
            reading = True
            out.append(line[len("description:") :].strip())
        elif reading and re.match(r"^[A-Za-z][A-Za-z0-9_-]*:", line):
            break
        elif reading:
            out.append(line.strip())
    if not out:
        raise SystemExit(f"{skill}/SKILL.md: no description")
    return " ".join(" ".join(out).split())


def plugin(arg):
    name, _, folder = arg.partition("=")
    skills = pathlib.Path(folder)
    if not name or not skills.is_dir():
        raise SystemExit(f"{arg}: expected <plugin>=<skills folder>")
    return {
        f"{name}:{s.name}": description(s)
        for s in sorted(skills.iterdir())
        if (s / "SKILL.md").is_file()
    }


def entry(name, desc):
    return f"- {name}: {desc} (file: r0/{name}/SKILL.md)"


def tokens(text):
    return round(len(text) / CHARS_PER_TOKEN)


def yaml_hazards(skills):
    """An unquoted description holding a colon-space is not valid YAML."""
    bad = []
    for skill in skills:
        for line in (skill / "SKILL.md").read_text().split("\n"):
            if line.startswith("description:"):
                value = line[len("description:") :].strip()
                if value[:1] not in "\"'>|" and ": " in value:
                    bad.append(f"{skill.name}: unquoted 'x: y' in description")
                break
    return bad


def main():
    name, args = sys.argv[1], sys.argv[2:]
    skills = [pathlib.Path(a) for a in args if "=" not in a]
    profile = {s.name: description(s) for s in skills}
    for arg in args:
        if "=" in arg:
            profile.update(plugin(arg))

    body = "\n".join(entry(n, d) for n, d in sorted(profile.items()))
    total = FIXED + tokens(body)
    state = "OVER" if total > BUDGET else ("tight" if total > TARGET else "ok")
    failed = total > BUDGET
    slack = (BUDGET - total) * CHARS_PER_TOKEN
    print(
        f"{name:9s} {len(profile):3d} skills  {len(body):6d} chars  "
        f"{total:5d}/{BUDGET} tokens  {state}  "
        f"{'trim' if total > BUDGET else 'room for'} {abs(slack):.0f} characters"
    )

    for problem in yaml_hazards(skills):
        failed = True
        print(f"FAIL {problem}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
