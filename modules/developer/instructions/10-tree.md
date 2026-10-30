## The tree

This folder holds one plain clone per roster repo, at `<group>/<repo>` unless its row sets another `dir`, and a `<group>/.worktrees` folder per group for task worktrees. The `dnix.developer` home-manager module owns the clones and this file: a switch clones a missing row and rewrites this file.
