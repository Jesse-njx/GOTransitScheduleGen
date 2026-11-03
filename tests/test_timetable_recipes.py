import json

import pytest

import timetable_recipes as recipes
from test_schedule import make_feed


def recipe(tmp_path, monkeypatch):
    # Keep real generator/export integration while substituting a tiny local feed.
    (tmp_path / 'feed.zip').write_bytes(b'fixture feed')
    monkeypatch.setattr(recipes.gk, 'read_feed', lambda *args, **kwargs: make_feed())
    path = tmp_path / 'recipe.json'
    path.write_text(json.dumps({'feed': 'feed.zip', 'duplicates': None, 'jobs': [
        {'name': 'corridor', 'dates': ['20261029'], 'routes': ['LW:1'], 'pdf': True},
    ]}))
    return path


def test_pack_contains_verifiable_outputs_and_source_manifest(tmp_path, monkeypatch):
    path = recipe(tmp_path, monkeypatch)
    output = tmp_path / 'pack'
    manifest = recipes.build_pack(path, output)
    assert manifest['feed']['sha256'] == recipes.file_hash(tmp_path / 'feed.zip')
    assert manifest['duplicate_mapping'] is None
    assert manifest['schedules'][0]['directions']['forward']['trips'] == 1
    assert len(manifest['schedules'][0]['files']) == 2
    for item in manifest['schedules'][0]['files']:
        assert recipes.file_hash(output / item['path']) == item['sha256']
    assert json.loads((output / 'manifest.json').read_text())['schema_version'] == 1


def test_existing_pack_is_never_overwritten(tmp_path, monkeypatch):
    path = recipe(tmp_path, monkeypatch)
    output = tmp_path / 'pack'
    output.mkdir()
    sentinel = output / 'keep.txt'
    sentinel.write_text('original')
    with pytest.raises(ValueError, match='already exists'):
        recipes.build_pack(path, output)
    assert sentinel.read_text() == 'original'


def test_later_job_failure_leaves_no_partial_pack(tmp_path, monkeypatch):
    path = recipe(tmp_path, monkeypatch)
    config = json.loads(path.read_text())
    config['jobs'].append({'name': 'bad-stops', 'dates': ['20261029'], 'routes': ['LW:1'], 'stops': ['MISSING']})
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='Unknown stop_ids'):
        recipes.build_pack(path, tmp_path / 'pack')
    assert not (tmp_path / 'pack').exists()
    assert not list(tmp_path.glob('.pack-*'))


@pytest.mark.parametrize('patch', [
    {'name': '../escape'}, {'dates': ['20261029', '20261029']}, {'dates': ['20261201']},
    {'routes': ['LW:2']}, {'pdf': 'false'}, {'stop': ['UN']},
])
def test_invalid_recipe_cannot_create_a_pack(tmp_path, monkeypatch, patch):
    path = recipe(tmp_path, monkeypatch)
    config = json.loads(path.read_text())
    config['jobs'][0].update(patch)
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError):
        recipes.build_pack(path, tmp_path / 'pack')
    assert not (tmp_path / 'pack').exists()


def test_relative_inputs_do_not_depend_on_current_directory(tmp_path, monkeypatch):
    path = recipe(tmp_path, monkeypatch)
    other = tmp_path / 'other'
    other.mkdir()
    monkeypatch.chdir(other)
    config, feed, mapping = recipes.load_recipe(path)
    assert feed == tmp_path / 'feed.zip'
    assert mapping is None


def test_excel_only_pack(tmp_path, monkeypatch):
    path = recipe(tmp_path, monkeypatch)
    config = json.loads(path.read_text())
    config['jobs'][0]['pdf'] = False
    path.write_text(json.dumps(config))
    manifest = recipes.build_pack(path, tmp_path / 'pack')
    assert len(manifest['schedules'][0]['files']) == 1
    assert not list((tmp_path / 'pack').rglob('*.pdf'))


def test_input_mutation_aborts_pack(tmp_path, monkeypatch):
    path = recipe(tmp_path, monkeypatch)
    original = recipes.generate_both_directions
    def changing_input(*args, **kwargs):
        result = original(*args, **kwargs)
        (tmp_path / 'feed.zip').write_bytes(b'changed while running')
        return result
    monkeypatch.setattr(recipes, 'generate_both_directions', changing_input)
    with pytest.raises(ValueError, match='Input changed'):
        recipes.build_pack(path, tmp_path / 'pack')
    assert not (tmp_path / 'pack').exists()
