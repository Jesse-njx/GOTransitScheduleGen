# Experiment: feed inspection before timetable production

## Hypothesis

A timetable author should not have to unzip GTFS files to find route IDs,
direction headsigns, service coverage, and stop names. This is a hypothesis about
the project's workflow, not a claim about GO Transit's internal systems.

## Try it

Use the existing Python environment and requirements. From the repository:

```sh
python feed_inspector.py --feed ../data/GO-GTFS.zip --date 20261029 \
  --routes LW 12 --search-stop Burlington --json output/feed-inventory.json
```

Omit the route and stop filters for the full inventory. Counts describe the
requested service date; headsigns describe all known patterns in that feed.
Direction IDs remain literal GTFS values, never assumed east/west labels.
The JSON includes feed version metadata when supplied by the source.

A date outside coverage produces a warning and exit status 2. A valid day with
no selected service remains a distinct result. Feed-declared coverage takes
precedence; missing bounds fall back to calendar/calendar_dates bounds. Those
bounds are coverage, not a promise of service on every enclosed date.

Stop IDs are raw GTFS IDs. This tool deliberately does not pretend to resolve
the generator's per-trip, priority-sensitive station mappings into one global
mapping. Existing timetable generation is unchanged.

## Owner decision

Would discovering inputs inside the tool save time? If yes, the next iteration
could turn selected route/direction rows into a saved timetable recipe. If the
owner already has an input catalog, this experiment can remain an optional CLI.

## Validation

`python -m pytest -q` runs baseline tests and inspection tests, including date
coverage, calendar exceptions, missing directions, literal search, and ambiguous
route names. No new dependencies.
