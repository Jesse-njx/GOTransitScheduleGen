"""Inspect available GO service before choosing timetable generator arguments."""

import argparse
from datetime import datetime
import json
from pathlib import Path

import gtfs_kit as gk
import pandas as pd

from ScheduleGen import METROLINX_ATTRIBUTION


def _text(value):
    return '' if pd.isna(value) else str(value)


def inspect_feed(feed, date, routes=None, stop_search=None):
    """Return JSON-safe inventory; direction IDs are never interpreted as compass directions."""
    if len(date) != 8 or not date.isdigit():
        raise ValueError('Date must use YYYYMMDD format.')
    datetime.strptime(date, '%Y%m%d')
    calendar_dates = feed.get_dates()
    metadata = [] if feed.feed_info is None else json.loads(feed.feed_info.to_json(orient='records'))
    declared = metadata[0] if metadata else {}
    start = _text(declared.get('feed_start_date')) or (calendar_dates[0] if calendar_dates else None)
    end = _text(declared.get('feed_end_date')) or (calendar_dates[-1] if calendar_dates else None)
    outside = bool((start and date < start) or (end and date > end))
    date_status = 'outside_feed_range' if outside else ('within_feed_range' if start and end else 'coverage_unknown')
    selected = feed.routes.copy()
    if routes:
        ids = []
        for selector in routes:
            match = selected[selected.route_id.astype(str).eq(str(selector))]
            if match.empty and 'route_short_name' in selected:
                match = selected[selected.route_short_name.astype(str).eq(str(selector))]
            if len(match) != 1:
                raise ValueError(f'Route {selector!r} is unknown or ambiguous; use an exact route_id.')
            ids.append(str(match.iloc[0].route_id))
        selected = selected[selected.route_id.astype(str).isin(ids)]
    all_trips = feed.trips[feed.trips.route_id.isin(selected.route_id)].copy()
    active = feed.get_trips(date)
    active = active[active.route_id.isin(selected.route_id)]
    calls = feed.stop_times[feed.stop_times.trip_id.isin(active.trip_id)]
    known_calls = feed.stop_times[feed.stop_times.trip_id.isin(all_trips.trip_id)]
    inventory = []
    for _, route in selected.sort_values('route_id').iterrows():
        route_trips = all_trips[all_trips.route_id.eq(route.route_id)]
        if 'direction_id' not in route_trips:
            route_trips = route_trips.assign(direction_id=None)
        for direction, group in route_trips.groupby('direction_id', dropna=False):
            day_trips = active[active.trip_id.isin(group.trip_id)]
            day_calls = calls[calls.trip_id.isin(day_trips.trip_id)]
            inventory.append({
                'route_id': str(route.route_id),
                'route_short_name': _text(route.get('route_short_name')),
                'route_long_name': _text(route.get('route_long_name')),
                'direction_id': None if pd.isna(direction) else int(direction),
                'headsigns': sorted(set(group.get('trip_headsign', pd.Series(dtype=str)).dropna().astype(str))),
                'active_trips': len(day_trips),
                'active_stops': day_calls.stop_id.nunique(),
            })
    stops = feed.stops[feed.stops.stop_id.isin(known_calls.stop_id)].copy()
    if stop_search:
        match = stops.stop_id.astype(str).str.contains(stop_search, case=False, regex=False)
        match |= stops.stop_name.astype(str).str.contains(stop_search, case=False, regex=False)
        stops = stops[match]
    call_counts = calls.stop_id.value_counts()
    stop_inventory = [{
        'stop_id': str(row.stop_id), 'stop_name': _text(row.stop_name),
        'active_calls': int(call_counts.get(row.stop_id, 0)),
    } for _, row in stops.sort_values(['stop_name', 'stop_id']).iterrows()]
    warnings = []
    if outside:
        warnings.append('Requested date is outside feed coverage; zero trips does not establish that no service exists.')
    if date_status == 'coverage_unknown':
        warnings.append('Feed coverage could not be established.')
    if not outside and active.empty:
        warnings.append('No active trips for the selected routes on this date.')
    if any(row['direction_id'] is None for row in inventory):
        warnings.append('Some trips lack direction_id; the current generator requires explicit 0/1 directions.')
    return {
        'date': date, 'date_status': date_status,
        'coverage': {'start': start, 'end': end}, 'feed_info': metadata,
        'active_trips': len(active), 'routes': inventory, 'stops': stop_inventory,
        'warnings': warnings,
        'attribution': METROLINX_ATTRIBUTION if feed.agency is not None and 'agency_name' in feed.agency
        and feed.agency.agency_name.astype(str).str.casefold().eq('go transit').any() else None,
        'stop_id_note': 'Raw feed IDs, before duplicate_stn.json. The generator expects canonical IDs for --stops.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feed', required=True)
    parser.add_argument('--date', required=True)
    parser.add_argument('--routes', nargs='+', help='Optional exact route IDs or unambiguous short names')
    parser.add_argument('--search-stop', help='Literal, case-insensitive stop ID or name search')
    parser.add_argument('--json', dest='json_path', help='Also write the complete inventory as JSON')
    args = parser.parse_args()
    try:
        report = inspect_feed(gk.read_feed(args.feed, dist_units='km'), args.date, args.routes, args.search_stop)
        if args.json_path:
            path = Path(args.json_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Coverage: {report['coverage']['start']} to {report['coverage']['end']}")
    print(f"Date: {report['date']} ({report['date_status']}); {report['active_trips']} active trips")
    for warning in report['warnings']:
        print(f'WARNING: {warning}')
    for route in report['routes']:
        print(f"{route['route_short_name']} | {route['route_id']}:{route['direction_id']} | "
              f"{route['active_trips']} trips | {'; '.join(route['headsigns'])}")
    print(report['stop_id_note'])
    for stop in report['stops']:
        print(f"{stop['stop_id']} | {stop['stop_name']} | {stop['active_calls']} calls")
    if report['attribution']:
        print(report['attribution'])
    return 2 if report['date_status'] == 'outside_feed_range' else 0


if __name__ == '__main__':
    raise SystemExit(main())
