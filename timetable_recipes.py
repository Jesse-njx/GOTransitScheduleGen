"""Build repeatable local timetable packs from a saved JSON recipe."""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import re
import shutil
import tempfile

import gtfs_kit as gk
import pandas as pd

from ScheduleGen import DEFAULT_DUP_MAP, generate_both_directions, resolve_route_pairs


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _keys(value, allowed, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object.')
    unknown = value.keys() - allowed
    if unknown:
        raise ValueError(f'Unknown {label} fields: {", ".join(sorted(unknown))}')


def load_recipe(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding='utf-8'))
    _keys(config, {'feed', 'duplicates', 'jobs'}, 'recipe')
    if not isinstance(config.get('feed'), str) or not config['feed']:
        raise ValueError('recipe.feed must name a local GTFS ZIP.')
    feed_path = (path.parent / config['feed']).resolve()
    if not feed_path.is_file() or feed_path.suffix.lower() != '.zip':
        raise ValueError('recipe.feed must be an existing local GTFS ZIP.')
    duplicates = config.get('duplicates', str(DEFAULT_DUP_MAP))
    if duplicates is not None and (not isinstance(duplicates, str) or not duplicates):
        raise ValueError('duplicates must be a path or null to disable station mapping.')
    mapping_path = None if duplicates is None else (path.parent / duplicates).resolve()
    if mapping_path is not None and not mapping_path.is_file():
        raise ValueError(f'Duplicate station mapping does not exist: {mapping_path}')
    jobs = config.get('jobs')
    if not isinstance(jobs, list) or not jobs:
        raise ValueError('jobs must be a nonempty list.')
    names = set()
    for job in jobs:
        _keys(job, {'name', 'title', 'dates', 'routes', 'stops', 'sort_stop', 'pdf'}, 'job')
        name = job.get('name')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name):
            raise ValueError('Job names must use letters, numbers, underscores, or hyphens (1-80 characters).')
        if name in names:
            raise ValueError(f'Duplicate job name: {name}')
        names.add(name)
        dates = job.get('dates')
        if not isinstance(dates, list) or not dates:
            raise ValueError(f'{name}: dates must be a nonempty list.')
        for date in dates:
            if not isinstance(date, str) or not re.fullmatch(r'\d{8}', date):
                raise ValueError(f'{name}: dates must be YYYYMMDD strings.')
            datetime.strptime(date, '%Y%m%d')
        if len(dates) != len(set(dates)):
            raise ValueError(f'{name}: duplicate dates would overwrite outputs.')
        routes = job.get('routes')
        if not isinstance(routes, list) or not routes or not all(isinstance(route, str) for route in routes):
            raise ValueError(f'{name}: routes must be a nonempty list of ROUTE:DIRECTION strings.')
        try:
            pairs = [(route, int(direction)) for route, direction in (s.rsplit(':', 1) for s in routes)]
        except ValueError:
            raise ValueError(f'{name}: use ROUTE:DIRECTION selectors, such as LW:1.') from None
        if any(not route or direction not in (0, 1) for route, direction in pairs):
            raise ValueError(f'{name}: directions must be 0 or 1.')
        if 'pdf' in job and not isinstance(job['pdf'], bool):
            raise ValueError(f'{name}: pdf must be true or false.')
        if 'title' in job and not isinstance(job['title'], str):
            raise ValueError(f'{name}: title must be a string.')
        if 'sort_stop' in job and not isinstance(job['sort_stop'], str):
            raise ValueError(f'{name}: sort_stop must be a canonical stop ID string.')
        if 'stops' in job and (not isinstance(job['stops'], list) or not job['stops'] or
                               not all(isinstance(s, str) and s for s in job['stops'])):
            raise ValueError(f'{name}: stops must be a nonempty list of canonical stop ID strings.')
    return config, feed_path, mapping_path


def _check_dates(feed, jobs):
    dates = feed.get_dates()
    info = {} if feed.feed_info is None or feed.feed_info.empty else feed.feed_info.iloc[0]
    def bound(field, fallback):
        value = info.get(field)
        return fallback if pd.isna(value) or value == '' else str(value)
    start = bound('feed_start_date', dates[0] if dates else None)
    end = bound('feed_end_date', dates[-1] if dates else None)
    if not start or not end:
        raise ValueError('Cannot establish feed coverage for this timetable pack.')
    for job in jobs:
        for date in job['dates']:
            if not start <= date <= end:
                raise ValueError(f"{job['name']}: {date} is outside feed coverage {start} to {end}.")


def build_pack(recipe_path, output):
    """Stage all files privately; expose the requested directory only after success."""
    recipe_path = Path(recipe_path).resolve()
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError(f'Output already exists; choose a new pack directory: {output}')
    config, feed_path, mapping_path = load_recipe(recipe_path)
    # Hash inputs before loading; verify them again before accepting the pack.
    inputs = [recipe_path, feed_path] + ([mapping_path] if mapping_path else [])
    input_hashes = {path: file_hash(path) for path in inputs}
    feed = gk.read_feed(feed_path, dist_units='km')
    _check_dates(feed, config['jobs'])
    pairs_by_job = {}
    for job in config['jobs']:
        pairs = [(route, int(direction)) for route, direction in (s.rsplit(':', 1) for s in job['routes'])]
        pairs_by_job[job['name']] = resolve_route_pairs(feed, pairs)
    source_dir = Path(__file__).parent
    manifest = {
        'schema_version': 1,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'recipe': {'name': recipe_path.name, 'sha256': input_hashes[recipe_path], 'content': config},
        'feed': {'name': feed_path.name, 'sha256': input_hashes[feed_path],
                 'info': [] if feed.feed_info is None else json.loads(feed.feed_info.to_json(orient='records'))},
        'duplicate_mapping': None if mapping_path is None else {'name': mapping_path.name, 'sha256': input_hashes[mapping_path]},
        'code_sha256': {name: file_hash(source_dir / name) for name in
                        ('ScheduleGen.py', 'schedule_ordering.py', 'schedule_pdf.py', 'timetable_recipes.py')},
        'runtime': {'python': platform.python_version(), 'packages': {name: version(name) for name in
                    ('gtfs-kit', 'pandas', 'xlsxwriter', 'reportlab')}},
        'schedules': [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f'.{output.name}-', dir=output.parent))
    try:
        for job in config['jobs']:
            for date in job['dates']:
                directory = staging / job['name'] / date
                excel = directory / 'schedule.xlsx'
                pdf = directory / 'schedule.pdf' if job.get('pdf', True) else None
                schedules = generate_both_directions(
                    feed, date, pairs_by_job[job['name']], dup_map_path=mapping_path,
                    out_excel=excel, out_pdf=pdf, title=job.get('title', job['name']),
                    stop_ids=job.get('stops'), trip_sort_stop=job.get('sort_stop'),
                )
                manifest['schedules'].append({
                    'job': job['name'], 'date': date, 'resolved_routes': pairs_by_job[job['name']],
                    'directions': {direction: {
                        'trips': len(frame), 'stop_ids': frame.attrs['stop_ids'],
                        'sort_stop': frame.attrs.get('trip_sort_stop'),
                        'no_service': frame.empty,
                    } for direction, frame in schedules.items()},
                    'files': [{'path': str(path.relative_to(staging)), 'sha256': file_hash(path)}
                              for path in (excel, pdf) if path is not None],
                })
        for path, digest in input_hashes.items():
            if file_hash(path) != digest:
                raise ValueError(f'Input changed while generating the pack: {path.name}; rerun with stable inputs.')
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        if output.exists() or output.is_symlink():
            raise ValueError(f'Output appeared during generation; choose a new directory: {output}')
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe', required=True, help='JSON recipe; input paths are relative to this file')
    parser.add_argument('--output', required=True, help='New local directory for the completed timetable pack')
    args = parser.parse_args()
    try:
        manifest = build_pack(args.recipe, args.output)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f"Built {len(manifest['schedules'])} timetable pairs in {args.output}")
    for entry in manifest['schedules']:
        counts = ', '.join(f"{direction}: {stats['trips']} trips" for direction, stats in entry['directions'].items())
        print(f"{entry['job']} {entry['date']} | {counts}")
    print('manifest.json records source, configuration, code, runtime and output hashes.')


if __name__ == '__main__':
    main()
