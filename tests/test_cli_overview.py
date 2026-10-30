"""Declared overview parser and compact renderer contracts (BACK-2375)."""
import json
from functools import partial

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.overview import OverviewAdapter
from reveal.cli.routing.declared import create_declared_parser
from reveal.rendering.adapters.overview import OverviewRenderer, overview_text

create_overview_parser = partial(create_declared_parser, 'overview')


def test_generated_parser_uses_compact_description_and_controls():
    parser = create_overview_parser()
    assert parser.prog == 'reveal overview'
    assert 'map' in parser.description
    args = parser.parse_args(['.', '--top', '0', '--no-imports', '--all'])
    assert args.top == '0' and args.no_imports is True and args.all is True


def test_help_and_schema_describe_same_result():
    assert OverviewAdapter.get_schema()['output_types'][0]['type'] == 'overview'
    assert 'map' in OverviewAdapter.get_help()['description']
    assert 'quality' not in OverviewAdapter.get_help()['description']


@pytest.mark.parametrize('format', ['typed', 'grep'])
def test_unsupported_format_is_usage_error(tmp_path, format):
    result = run('overview', tmp_path, '--format', format)
    assert result.returncode == 2
    assert 'text' in result.stderr and 'json' in result.stderr


def test_text_and_json_render_already_projected_map(tmp_path):
    (tmp_path / 'a.py').write_text('VALUE=1\n', encoding='utf-8')
    body = OverviewAdapter(str(tmp_path), 'top=0').get_structure()
    text = overview_text(body)
    assert '1 recognized code files' in text
    assert 'showing 0 of 1 observed' in text
    assert OverviewRenderer.exit_code(body) == 0
    result = run('overview', tmp_path, '--format', 'json')
    assert result.returncode == 0 and json.loads(result.stdout)['map_status'] == 'complete'
