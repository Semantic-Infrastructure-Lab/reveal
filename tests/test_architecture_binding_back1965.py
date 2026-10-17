"""Declared architecture controls retain their analysis population and codec roles."""
from argparse import Namespace

import pytest

from reveal.adapters.architecture import ArchitectureAdapter
from reveal.utils.query_binding import bind_declared_params


@pytest.mark.parametrize('top,expected', [(None, 20), (0, 0), (2, 8)])
@pytest.mark.parametrize('transport', ['typed', 'uri'])
def test_ordinary_analysis_population(tmp_path, monkeypatch, top, expected, transport):
    source = {} if top is None else {'top': top}
    query = '' if top is None else f'top={top}'
    params = bind_declared_params(ArchitectureAdapter.PARAM_SPECS,
                                  source if transport == 'typed' else query, transport=transport)
    seen = []
    monkeypatch.setattr('reveal.adapters.architecture._run_combined_analysis',
                        lambda adapter, path, limit: (seen.append(limit) or [], {}))
    ArchitectureAdapter(str(tmp_path), params=params).get_structure()
    assert seen == [expected]


def test_validation_preserves_omitted_controls_and_read_accounting():
    from reveal.utils.query_parser import collect_query_keys
    with collect_query_keys() as keys:
        params = bind_declared_params(ArchitectureAdapter.PARAM_SPECS, 'top=2', transport='uri')
        ArchitectureAdapter.validate_request(params, Namespace(verbose=False))
        assert keys.used == set()
        assert set(dict.keys(params)) == {'top'}


@pytest.mark.parametrize('top,expected', [(None, 20), (0, 4), (2, 8)])
def test_diff_population_preserves_existing_multiplier(tmp_path, monkeypatch, top, expected):
    from reveal.diff import architecture_diff
    from reveal.utils.results import ResultBuilder
    # Request validation is covered with actual repositories by the CLI harness.
    monkeypatch.setattr(architecture_diff, '_open_repo', lambda path: object())
    monkeypatch.setattr(architecture_diff, '_resolve_commit', lambda repo, ref: object())
    seen = []
    def compare(path, ref, *, top_n):
        seen.append(top_n)
        return ResultBuilder.create('architecture_diff', str(path), data={'analysis': {'complete': True}})
    monkeypatch.setattr(architecture_diff, 'run_architecture_diff', compare)
    values = {'against': 'HEAD'}
    if top is not None:
        values['top'] = top
    ArchitectureAdapter(str(tmp_path), params=values).get_structure()
    assert seen == [expected]


@pytest.mark.parametrize('verbose', [False, True])
def test_verbose_changes_analysis_but_all_does_not(tmp_path, monkeypatch, verbose):
    from reveal.adapters.overview import UNLIMITED_TOP
    seen = []
    monkeypatch.setattr('reveal.adapters.architecture._run_combined_analysis',
                        lambda adapter, path, limit: (seen.append(limit) or [], {}))
    ArchitectureAdapter(str(tmp_path)).get_structure(verbose=verbose, all=True)
    assert seen == [UNLIMITED_TOP * 4 if verbose else 20]


@pytest.mark.parametrize('warning,incomplete', [
    ('partial_parse', True), ('worker_lost', True), ('analysis_failed', True),
    ('parse_recovered', True), ('complexity_is_unweighted', False), ('truncated', False),
])
def test_explicit_missing_evidence_taxonomy(warning, incomplete):
    from reveal.utils.results import AnalysisCompleteness, ResultBuilder
    result = ResultBuilder.create('architecture', '.', confidence=0.0,
                                  warnings=[{'type': warning, 'message': 'producer evidence'}])
    facts = ArchitectureAdapter.execution_facts(result)
    assert (facts.completeness is AnalysisCompleteness.INCOMPLETE) is incomplete
