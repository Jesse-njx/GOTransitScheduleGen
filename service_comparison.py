"""Compare scheduled service without treating regenerated trip IDs as changes."""

import argparse
from collections import defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path

import gtfs_kit as gk
import pandas as pd

from ScheduleGen import METROLINX_ATTRIBUTION, resolve_route_pairs
from schedule_ordering import time_seconds


def _text(value):
    return '' if pd.isna(value) else str(value)


def _validate_date(feed, date):
    if len(date) != 8 or not date.isdigit():
        raise ValueError('Dates must use YYYYMMDD format.')
    datetime.strptime(date, '%Y%m%d')
    dates = feed.get_dates()
    info = {} if feed.feed_info is None or feed.feed_info.empty else feed.feed_info.iloc[0]
    start = _text(info.get('feed_start_date')) or (dates[0] if dates else None)
    end = _text(info.get('feed_end_date')) or (dates[-1] if dates else None)
    if not start or not end:
        raise ValueError('Cannot establish feed coverage; comparison would be unreliable.')
    if not start <= date <= end:
        raise ValueError(f'Date {date} is outside feed coverage {start} to {end}.')


def _snapshot(feed, date, route_id, direction):
    active = feed.get_trips(date)
    if 'direction_id' not in active:
        raise ValueError('This comparison requires explicit GTFS direction_id values.')
    active = active[active.route_id.eq(route_id) & active.direction_id.eq(direction)]
    if feed.frequencies is not None and feed.frequencies.trip_id.isin(active.trip_id).any():
        raise ValueError('Frequency-based service is not supported by this scheduled-trip comparison.')
    calls = feed.stop_times[feed.stop_times.trip_id.isin(active.trip_id)].copy()
    calls['stop_sequence'] = pd.to_numeric(calls.stop_sequence, errors='raise')
    groups = dict(tuple(calls.groupby('trip_id', sort=False)))
    result = defaultdict(list)
    for _, trip in active.sort_values('trip_id').iterrows():
        if trip.trip_id not in groups:
            raise ValueError(f'Active trip {trip.trip_id!r} has no stop times.')
        sequence = []
        for _, row in groups[trip.trip_id].sort_values('stop_sequence', kind='stable').iterrows():
            times = []
            for field in ('arrival_time', 'departure_time'):
                value = _text(row.get(field))
                # Normalize equivalent GTFS clock strings without losing seconds or service days.
                times.append(None if not value else int(time_seconds(value)))
            permissions = [0 if pd.isna(row.get(field)) else int(row[field])
                           for field in ('pickup_type', 'drop_off_type')]
            sequence.append((str(row.stop_id), *times, *permissions))
        signature = tuple(sequence)
        result[signature].append({
            'trip_id': str(trip.trip_id), 'headsign': _text(trip.get('trip_headsign')),
            'calls': [dict(zip(('stop_id', 'arrival_seconds', 'departure_seconds', 'pickup_type', 'drop_off_type'), call))
                      for call in sequence],
        })
    return result


def compare_service(before, after, before_date, after_date, pairs):
    """Match multisets of exact call patterns; do not guess one-to-one retiming matches."""
    _validate_date(before, before_date)
    _validate_date(after, after_date)
    if not pairs:
        raise ValueError('Select at least one route/direction pair.')
    summaries, changes, seen = [], [], set()
    for selector, direction in pairs:
        before_route, direction = resolve_route_pairs(before, [(selector, direction)])[0]
        after_route, _ = resolve_route_pairs(after, [(selector, direction)])[0]
        key = (before_route, after_route, direction)
        if key in seen:
            continue
        seen.add(key)
        old = _snapshot(before, before_date, before_route, direction)
        new = _snapshot(after, after_date, after_route, direction)
        unchanged = 0
        removed, added = [], []
        # repr supplies deterministic ordering even when a time is missing (None).
        for signature in sorted(old.keys() | new.keys(), key=repr):
            old_rows, new_rows = old.get(signature, []), new.get(signature, [])
            matched = min(len(old_rows), len(new_rows))
            unchanged += matched
            removed.extend(old_rows[matched:])
            added.extend(new_rows[matched:])
        summaries.append({
            'route': str(selector), 'direction_id': direction,
            'before_route_id': before_route, 'after_route_id': after_route,
            'before_trips': sum(map(len, old.values())), 'after_trips': sum(map(len, new.values())),
            'unchanged': unchanged, 'removed': len(removed), 'added': len(added),
        })
        for change, rows in [('removed', removed), ('added', added)]:
            changes.extend(dict(change=change, route=str(selector), direction_id=direction, **row) for row in rows)
    return {
        'before_date': before_date, 'after_date': after_date, 'routes': summaries, 'changes': changes,
        'feed_info': {label: [] if feed.feed_info is None else json.loads(feed.feed_info.to_json(orient='records'))
                      for label, feed in [('before', before), ('after', after)]},
        'attribution': METROLINX_ATTRIBUTION if any(
            feed.agency is not None and 'agency_name' in feed.agency
            and feed.agency.agency_name.astype(str).str.casefold().eq('go transit').any()
            for feed in (before, after)) else None,
        'comparison_basis': 'Exact ordered raw stop IDs, arrival/departure service-day seconds, pickup/drop-off types; multiplicity preserved.',
        'limitations': [
            'Retimed trips appear as one removal and one addition; no automatic cancellation or one-to-one retiming inference.',
            'Stop ID changes appear as service changes. Route IDs may change when the same unambiguous short name resolves in each feed.',
            'Trip IDs and headsign text are not matching keys. This report compares scheduled calls, not every GTFS field.',
            'This report does not apply duplicate_stn.json or infer connections. Frequency-based trips are rejected.',
        ],
    }


def write_report(report, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'comparison.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    notes = [report['comparison_basis'], *report['limitations']]
    if report['attribution']:
        notes.append(report['attribution'])
    (output / 'README.txt').write_text('\n\n'.join(notes) + '\n', encoding='utf-8')
    columns = ['change', 'route', 'direction_id', 'trip_id', 'headsign', 'calls']
    with (output / 'changed-trips.csv').open('w', newline='', encoding='utf-8') as target:
        writer = csv.DictWriter(target, fieldnames=columns)
        writer.writeheader()
        for change in report['changes']:
            writer.writerow(dict(change, calls=json.dumps(change['calls'], ensure_ascii=False)))
    with (output / 'summary.csv').open('w', newline='', encoding='utf-8') as target:
        writer = csv.DictWriter(target, fieldnames=list(report['routes'][0]))
        writer.writeheader()
        writer.writerows(report['routes'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-feed', required=True)
    parser.add_argument('--after-feed', required=True)
    parser.add_argument('--before-date', required=True)
    parser.add_argument('--after-date', required=True)
    parser.add_argument('--routes', nargs='+', required=True, metavar='ROUTE:DIRECTION')
    parser.add_argument('--output', required=True, help='Directory for comparison.json and CSV reports')
    args = parser.parse_args()
    try:
        pairs = [(route, int(direction)) for route, direction in (value.rsplit(':', 1) for value in args.routes)]
        before = gk.read_feed(args.before_feed, dist_units='km')
        after = before if args.before_feed == args.after_feed else gk.read_feed(args.after_feed, dist_units='km')
        report = compare_service(before, after, args.before_date, args.after_date, pairs)
        report['sources'] = {'before': args.before_feed, 'after': args.after_feed}
        write_report(report, args.output)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    for row in report['routes']:
        print(f"{row['route']}:{row['direction_id']}: {row['before_trips']} -> {row['after_trips']} trips; "
              f"{row['unchanged']} unchanged, {row['removed']} removed observations, {row['added']} added observations")
    print(f'Report: {args.output}')


if __name__ == '__main__':
    main()
