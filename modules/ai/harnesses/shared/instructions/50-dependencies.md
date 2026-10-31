
---

## DEPENDENCY MANAGEMENT

Before using ANY library, read its current docs and follow the latest patterns they show.

IMPORTANT: **Reproducible builds, always. No floating versions.**

The mechanism depends on the ecosystem:

- **npm / pip / uv** - pin exact in the manifest. `"react": "18.2.0"`, `numpy==1.24.3`. Never `^`, `~`, `latest`.
- **Rust / Cargo** - use the caret-range idiom (`"2.0.18"`) in `Cargo.toml` **and commit `Cargo.lock`**. The lockfile is the pin. Do NOT use `=X.Y.Z` in the manifest - it blocks `cargo update` from pulling security patches, which is a Cargo anti-pattern.
- **Go** - `go.mod` + committed `go.sum`. Both mandatory.
