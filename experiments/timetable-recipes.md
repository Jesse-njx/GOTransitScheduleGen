# Experiment: repeatable timetable production

## Hypothesis

The owner repeatedly generates the same corridor for several dates. Saving the
inputs as a recipe and producing one traceable pack could replace manual command
editing and reduce uncertainty about which feed produced which PDF.

## Try it

```sh
python timetable_recipes.py --recipe examples/lakeshore-week.json \
  --output output/lakeshore-review
```

The example uses the locally tested October 28-November 27, 2026 feed and produces
weekday, Saturday, and Sunday schedules. Adjust the dates and inputs for your
feed. The GTFS ZIP is not included. Input paths are relative to the recipe file,
not the shell's current directory. The output argument is relative to the shell.

Each job supplies a unique `name`, `dates`, and `routes`. Optional `title`,
`stops`, and `sort_stop` have the existing generator's semantics. `pdf` defaults
to true; false produces Excel only. Top-level `duplicates` defaults to the
repository's station mapping; set null to disable mapping or provide a path.

The result contains `<job>/<date>/schedule.xlsx`, optional `schedule.pdf`, and
`manifest.json`. Every Excel/PDF contains both directions. The manifest records
the recipe content, feed metadata, input and output SHA-256 hashes, generator
source hashes, dependency versions, row counts, stop IDs, sorting timepoints,
and no-service directions. Preserve the source ZIP and mapping separately:
hashes identify inputs but cannot reconstruct them.

All outputs are generated in a temporary sibling directory and moved into place
only when every job succeeds. Existing pack directories are refused. Failure
cleans up the temporary pack; the original feed and prior packs remain intact.
Dates outside declared coverage (or calendar bounds when absent) are rejected.

This creates local review files, not an official publication, upload, or approval.
The manifest aids reproducibility; PDF/Excel bytes are not promised identical
between runs because export metadata can include timestamps. Recipes inherit
the generator's documented limitations, including no frequency expansion or
transfer planning. There is no GUI or scheduling service.

## Owner decision

Does the real workflow generate a family of timetables repeatedly? If yes, ask
the owner to supply one actual corridor recipe. If not, retain the original CLI
and discard this optional layer. No new dependencies or core generator changes.

## Validation

`python -m pytest -q` checks real Excel/PDF export, file hashes, failed later jobs,
existing-pack protection, relative paths, invalid recipes, Excel-only mode, and
inputs modified during generation. The example is also exercised against the
local GO feed.
