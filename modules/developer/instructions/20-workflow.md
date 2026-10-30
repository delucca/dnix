## Workflow

A task gets its own git worktree, cut from the clone into `<group>/.worktrees/<repo>.<task>`. The clone itself stays on the trunk. A repo's own `AGENTS.md` wins where it says otherwise.

- **Landing** - merges land on the forge, or through a push from the worktree.
- **Removing it** - remove the worktree with `git worktree remove` once every commit on it is already on a remote.

If the user explicitly says to work in the clone for a given task, honor it, but confirm first.
