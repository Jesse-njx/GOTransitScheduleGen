import pandas as pd
import pytest

from feed_inspector import inspect_feed
from test_schedule import make_feed


def test_inventory_explains_directions_and_searches_names():
    report = inspect_feed(make_feed(), '20261029', ['LW'], 'union')
    assert report['active_trips'] == 2
    assert {r['direction_id'] for r in report['routes']} == {0, 1}
    assert [s['stop_id'] for s in report['stops']] == ['UN']
    assert report['stops'][0]['active_calls'] == 2


def test_out_of_range_differs_from_a_day_without_service():
    feed = make_feed()
    feed.feed_info = pd.DataFrame([{'feed_start_date': '20261001', 'feed_end_date': '20261031'}])
    inside = inspect_feed(feed, '20261030')
    outside = inspect_feed(feed, '20261101')
    assert inside['active_trips'] == outside['active_trips'] == 0
    assert inside['date_status'] == 'within_feed_range'
    assert outside['date_status'] == 'outside_feed_range'
    assert 'does not establish' in outside['warnings'][0]


def test_calendar_date_exception_removes_service():
    feed = make_feed()
    feed.calendar_dates['exception_type'] = 2
    report = inspect_feed(feed, '20261029')
    assert report['active_trips'] == 0
    assert report['date_status'] == 'within_feed_range'


def test_missing_direction_is_explained_instead_of_hidden():
    feed = make_feed()
    feed.trips = feed.trips.drop(columns='direction_id')
    report = inspect_feed(feed, '20261029')
    assert all(r['direction_id'] is None for r in report['routes'])
    assert any('direction_id' in w for w in report['warnings'])


def test_route_ambiguity_requires_exact_id():
    feed = make_feed()
    feed.routes['route_short_name'] = 'shared'
    with pytest.raises(ValueError, match='ambiguous'):
        inspect_feed(feed, '20261029', ['shared'])


def test_versioned_route_ids_and_literal_stop_search():
    feed = make_feed()
    feed.routes.loc[feed.routes.route_id.eq('LW'), 'route_id'] = 'version-LW'
    feed.trips.loc[feed.trips.route_id.eq('LW'), 'route_id'] = 'version-LW'
    assert inspect_feed(feed, '20261029', ['LW'])['active_trips'] == 2
    assert inspect_feed(feed, '20261029', stop_search='[')['stops'] == []
