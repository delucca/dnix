"""Check agent-md.py's output is a shape agy loads and can run: agy drops an
agent whose model is not one of its tiers without a word, refuses one that
names a tool outside its registry, and gives one with no tools list none.

Usage: antigravity-agents.py RENDERED_DIR
"""
import pathlib
import sys

import yaml

REGISTRY = {
    "ask_question", "define_subagent", "find_by_name", "grep_search", "invoke_subagent",
    "list_dir", "manage_subagents", "manage_task", "read_url_content", "replace_file_content",
    "run_command", "schedule", "search_web", "send_message", "view_file", "write_to_file",
}

files = sorted(pathlib.Path(sys.argv[1]).glob("*.md"))
bad = [] if files else ["no agent rendered"]
for f in files:
    front_text, _, body = f.read_text(encoding="utf-8")[4:].partition("\n---\n")
    front = yaml.safe_load(front_text)
    if set(front) - {"name", "description", "model", "tools"}:
        bad.append(f"{f.name}: unexpected keys {sorted(set(front) - {'name', 'description', 'model', 'tools'})}")
    if front.get("model", "pro") not in ("pro", "flash"):
        bad.append(f"{f.name}: model {front['model']!r} is not an agy tier")
    if not front.get("tools"):
        bad.append(f"{f.name}: no tools, so agy gives it none")
    elif set(front["tools"]) - REGISTRY:
        bad.append(f"{f.name}: tools outside agy's registry {sorted(set(front['tools']) - REGISTRY)}")
    if front.get("name") != f.stem:
        bad.append(f"{f.name}: name {front.get('name')!r} does not match the file")
    if not front.get("description") or not body.strip():
        bad.append(f"{f.name}: empty description or body")

for line in bad:
    print(f"FAIL: {line}")
print(f"{len(files)} agents, {len(bad)} problems")
sys.exit(1 if bad else 0)
