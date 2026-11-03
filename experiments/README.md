# Timetable production experiments

These are runnable proposals for the repository owner, not an agreed product
roadmap or a claim that this repository is affiliated with GO Transit.

## Working hypothesis

The original code focuses on combining bus/rail stops, ordering branching
corridors, and exporting both directions to Excel. Our guess is that the useful
product is a small timetable production workbench: discover source inputs,
review service differences, and generate repeatable packs for human review.
Replacing a transit agency's internal systems is not an established requirement.

Three independent branches start from upstream merge `c6dd4d3`. The combined
`experiment/timetable-workbench` branch includes all three. Existing generator
behavior and runtime dependencies are unchanged.

| Branch | Question it explores | Instructions |
| --- | --- | --- |
| `experiment/feed-inspector` | Can authors find usable dates, routes, directions, and stops without reading raw GTFS? | [Feed inspector](feed-inspector.md) |
| `experiment/service-comparison` | Can authors review changed service without false differences from trip ID churn? | [Service comparison](service-comparison.md) |
| `experiment/timetable-recipes` | Can one saved recipe rebuild a family of traceable timetables? | [Timetable recipes](timetable-recipes.md) |

## Try the workflow

Install the existing `requirements-dev.txt`, obtain a local GTFS ZIP, and run
commands from the repository directory. The examples use a feed covering
October 28-November 27, 2026. Substitute dates covered by your own feed.

1. Run `feed_inspector.py` to identify route/direction selectors and raw stop IDs.
2. Review the existing station mapping and edit `examples/lakeshore-week.json`.
   The inspector does not convert raw IDs into canonical display IDs.
3. Run `timetable_recipes.py` to produce a new local pack and its manifest.
4. When another feed is available, use `service_comparison.py` to review the
   selected routes. It compares raw calls, not generated PDFs or station aliases.

Each tool exposes `--help`. The individual instruction files contain full
commands and explain assumptions. Nothing is uploaded or officially published
by these tools, and they do not determine transfers or real-time service.

## What was actually tested

- Independent branches: 39 inspector, 41 comparison, and 45 recipe tests passed,
  each including the 33 existing tests. Combined branch: 59 tests passed.
- The local GO feed was inspected for LW and route 12.
- Service comparison was exercised on weekday versus Saturday in the **same**
  feed. Two-feed ID churn is covered by fixtures; a second historical feed was
  not available for a real release-to-release comparison.
- The recipe generated three dual-direction Excel/PDF pairs for October 29,
  October 31, and November 1: 660 total trip rows across both directions.
  All output hashes were verified. Each PDF had eight pages, both directions,
  and Metrolinx attribution; workbook sheets were checked programmatically.
  No new visual layout review was performed; the existing exporter is reused.
- Validation used the local Python 3.14 environment, not a multi-version CI matrix.

## Decisions for the owner

Which output do you actually need to produce, and who checks it? Is the slowest
part finding inputs, reviewing changes, or rebuilding published tables? One
representative real workflow would tell us which experiment deserves another
iteration. These branches can be accepted independently or discarded.

My strongest guess is the recipe experiment: the original script already
hardcoded a date, a feed path, and several route/direction pairs, which is the
beginning of a reusable publishing recipe. The inspector and comparison tools
support that workflow. A graphical editor can wait until these inputs and review
steps match the owner's actual process.
