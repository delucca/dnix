## Adding repos

Add a row to `dnix.developer.repositories` in the host's home-manager config and switch.

- **New repo** - add `{ path; url; }`. The next switch clones it.
- **Where it lands** - `dir` is the path under the root and defaults to `path`, so `delucca/dmacs` clones to `delucca/dmacs`. Set `dir` only for a repo that belongs somewhere else, such as a member repo nested under its wrapper repo's clone.
- **Other fields** - `name` is the label in warnings and the session name, and defaults to the last segment of `path`. `addDirs` lists the directories an agent session adds, relative to the clone, and defaults to `[ "." ]`.
- **Fork** - a fork's public repo goes on its row as `upstream`; the switch keeps both remotes of every clone in line with the rows.
