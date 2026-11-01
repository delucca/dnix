"""Reads a skill's secret at use time through the command dnix.ai.secrets.readCommand names."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

AI_DIR = Path.home() / ".config" / "ai"


def settings(skill: str) -> dict:
    """The skill's ``~/.config/ai/settings/<skill>.json``, or ``{}`` when it has none."""
    path = AI_DIR / "settings" / f"{skill}.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"{path} is not valid JSON: {e}")


def read(skill: str, key: str, *, label: str | None = None, timeout: int = 30) -> str:
    """Run the reader on ``settings.secrets.<key>``; any failure ``sys.exit``s with guidance."""
    label = label or key
    reader = AI_DIR / "secrets.json"
    command = json.loads(reader.read_text()).get("readCommand") if reader.is_file() else None
    if not command:
        sys.exit(f"{label} unavailable: no secret reader. Set dnix.ai.secrets.readCommand, or enable dnix.ai.opAgent.")

    ref = (settings(skill).get("secrets") or {}).get(key)
    if not ref:
        sys.exit(f"{label} unavailable: set dnix.ai.skills.{skill}.settings.secrets.{key}.")

    try:
        result = subprocess.run([*command, ref], capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        sys.exit(f"{label} unavailable: {command[0]} is not on PATH.")
    except subprocess.TimeoutExpired:
        sys.exit(f"Timed out reading {label} ({ref}) through {command[0]}.")

    if result.returncode != 0:
        sys.exit(f"Failed to read {label} from {ref} ({command[0]} exit {result.returncode}).\n"
                 f"stderr: {result.stderr.strip()}")
    value = result.stdout.strip()
    if not value:
        sys.exit(f"{command[0]} returned an empty {label} for {ref}.")
    return value
