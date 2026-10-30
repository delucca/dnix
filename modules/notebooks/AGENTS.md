# Notebooks

`~/Notebooks` holds one folder per notebook. Your session belongs to one of them: its folder is one of your added directories, and its `notebook.org` is the notebook. Your working directory is `~/Developer`, not the notebook, so write paths in full.

Write only inside your own notebook folder; notes and sources go through the bilbo skills, nowhere else. Never write into `archive/` or at the top of `~/Notebooks`.

## Layout of a notebook

- `notebook.org` is the notebook. The user writes it. Do not edit it unless asked; report in the session and the user records what matters.
- `work/` holds raw output: run logs, evidence, patches, prototypes, clones, downloads. Anything bulky or reproducible goes here. Ask before deleting anything under it. It is the record.
- `assets/` holds only the images `notebook.org` shows. Put nothing else there.
- `spec/` holds the one-pagers and decisions of a project, in `spec/one-pagers/` and `spec/decisions/`, until they move to its repo's `spec/`. Only the `spec` skill writes there.
- Nothing loose at the notebook root. Create `work/` or `assets/` when first needed.
- A `notes/` or `library/` folder left in a notebook is frozen: never read, search or write it.

## Notes and sources

- Notes and library sources live in bilbo's store, never in a notebook.
- Write a note with the `bilbo:note` skill, search the notes with `bilbo:recall`, answer from the sources with `bilbo:reference`, and add a page or PDF as a source with `bilbo:ingest`. Never write a note or a source by hand.
- Keep a note short and the evidence complete: the note says what was found and points at the files under `work/` that show it, by absolute path.
- Cite a source as `bilbo:<id>#<heading> "<quote>"`, the quote at least six words copied from what `bilbo library read` printed, never recalled. Check an answer with `bilbo cite` before handing it on.
