import copy

import pandas as pd
import pytest

from service_comparison import compare_service, write_report
from test_schedule import make_feed


def compare(before, after):
    return compare_service(before, after, '20261029', '20261029', [('LW', 1)])


def test_trip_and_route_id_churn_does_not_look_like_service_change():
    before = make_feed()
    after = copy.deepcopy(before)
    after.trips['trip_id'] = 'new-' + after.trips.trip_id
    after.stop_times['trip_id'] = 'new-' + after.stop_times.trip_id
    after.routes['route_id'] = 'new-' + after.routes.route_id
    after.trips['route_id'] = 'new-' + after.trips.route_id
    report = compare(before, after)
    assert report['routes'][0]['unchanged'] == 1
    assert report['changes'] == []


def test_retimming_preserves_seconds_and_after_midnight_service_day():
    before = make_feed([('LW', 'night', 1, [('NI', '23:00:00'), ('UN', '25:10:01')])])
    after = copy.deepcopy(before)
    after.stop_times.loc[after.stop_times.stop_id.eq('UN'), 'departure_time'] = '25:10:02'
    report = compare(before, after)
    assert report['routes'][0]['removed'] == report['routes'][0]['added'] == 1
    assert report['changes'][1]['calls'][-1]['departure_seconds'] == 90602


def test_identical_trip_multiplicity_is_preserved():
    calls = [('NI', '08:00:00'), ('UN', '09:00:00')]
    before = make_feed([('LW', 'one', 1, calls), ('LW', 'two', 1, calls)])
    after = make_feed([('LW', 'new', 1, calls)])
    summary = compare(before, after)['routes'][0]
    assert (summary['unchanged'], summary['removed'], summary['added']) == (1, 1, 0)


def test_boarding_restriction_change_is_visible():
    before = make_feed()
    after = copy.deepcopy(before)
    after.stop_times['pickup_type'] = 1
    assert compare(before, after)['routes'][0]['added'] == 1


def test_out_of_coverage_is_rejected_instead_of_reporting_cancellation():
    feed = make_feed()
    with pytest.raises(ValueError, match='outside feed coverage'):
        compare_service(feed, feed, '20261029', '20270101', [('LW', 1)])


def test_valid_day_without_service_reports_removed_observations():
    feed = make_feed()
    feed.feed_info = pd.DataFrame([{'feed_start_date': '20261001', 'feed_end_date': '20261031'}])
    report = compare_service(feed, feed, '20261029', '20261030', [('LW', 1)])
    assert report['routes'][0]['after_trips'] == 0
    assert report['routes'][0]['removed'] == 1


def test_frequency_service_is_not_counted_as_one_departure():
    feed = make_feed()
    feed.frequencies = pd.DataFrame([{'trip_id': 'day-LW-1'}])
    with pytest.raises(ValueError, match='Frequency-based'):
        compare(feed, feed)


def test_unknown_routes_fail_and_reports_are_machine_readable(tmp_path):
    feed = make_feed()
    with pytest.raises(ValueError, match='unknown'):
        compare_service(feed, feed, '20261029', '20261029', [('missing', 1)])
    report = compare(feed, feed)
    write_report(report, tmp_path)
    assert len(pd.read_csv(tmp_path / 'summary.csv')) == 1
    assert pd.read_csv(tmp_path / 'changed-trips.csv').empty
