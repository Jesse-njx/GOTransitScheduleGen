# Experiment: service change review

## Hypothesis

Before distributing a new timetable, its author wants to know which scheduled
calls changed. Comparing raw trip IDs creates noise when a feed regenerates IDs.
This experiment compares exact call patterns and retains duplicate trips.

## Try it

```sh
python service_comparison.py \
  --before-feed ../data/GO-GTFS.zip --after-feed ../data/GO-GTFS.zip \
  --before-date 20261029 --after-date 20261031 \
  --routes LW:0 LW:1 12:0 12:1 --output output/service-comparison
```

This example compares weekday and Saturday service in one feed, **not** two
historical feed releases. To review a feed update, supply two local ZIPs and
dates covered by their respective calendars. Prefer public route short names
when route IDs change between versions. Both feeds must contain each selected
route; unknown/ambiguous routes are errors rather than assumed cancellations.

Outputs:

- `summary.csv`: before/after totals, unchanged patterns, removed and added observations.
- `changed-trips.csv`: full trip IDs, headsigns, and ordered call details for review.
- `comparison.json`: complete report, matching rules, and limitations.
- `README.txt`: report interpretation and GO data attribution when applicable.

Matching uses raw stop IDs, arrival and departure seconds since service-day
midnight, and pickup/drop-off types. Seconds and hours past 24 are preserved.
Trip ID and headsign changes alone do not count as schedule changes. Two trips
with identical calls count twice. A retimed trip is a removal plus an addition;
the tool does not guess which of several similar trips was retimed.

Dates outside feed coverage and frequency-based service are rejected. This is
not a full GTFS validator, stop-ID migration tool, transfer planner, or proof
that a removed observation is a cancelled real-world trip. Duplicate station
mapping is intentionally excluded so physical stop changes remain visible.

## Owner decision

Is a review report useful before publishing schedules? If yes, the next step is
human-reviewed pairing of retimed trips and an explicit cross-feed stop map.
The existing timetable generator is unchanged; no new dependencies.

## Validation

`python -m pytest -q` covers ID churn, multiplicity, seconds after midnight,
boarding restrictions, no-service dates, invalid coverage, and frequency trips.
