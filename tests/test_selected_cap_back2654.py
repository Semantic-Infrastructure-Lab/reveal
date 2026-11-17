"""The cap of the answer a request selects (BACK-2654 Step 5): an answer selector (role='operation') may declare the
control that caps the rows of the answer it selects, which the global --all lifts. ``selected_cap`` reads it from a
raw query, before the binder runs, without marking any key used."""
from reveal.utils.query_binding import boolean_value, selected_cap
from reveal.utils.query_parser import ParamSpec

RANKING = ParamSpec('ranking', 'boolean', 'Legacy ranking answer', False, boolean_value, role='operation',
                    cap='top', aliases=('rank_legacy',))
VIEW = ParamSpec('view', 'string', 'Views', None, str, role='operation', choices=('hot',))
NOT_AN_ANSWER = ParamSpec('flavor', 'boolean', 'A setting', False, boolean_value, role='analysis', cap='other')
DECLARATIONS = (VIEW, RANKING, NOT_AN_ANSWER)


def test_a_selected_answer_names_its_declared_cap():
    for query in ('ranking=true', 'ranking', 'ranking=1', 'a=1&ranking=on', 'rank_legacy=true', 'rank%5Flegacy=true'):
        assert selected_cap(DECLARATIONS, query) == 'top', query


def test_an_answer_not_selected_or_without_a_cap_names_none():
    for query in ('', 'ranking=false', 'ranking=0', 'view=hot', 'flavor=true', 'rankings=true', 'xranking=true'):
        assert selected_cap(DECLARATIONS, query) is None, query
    assert selected_cap((VIEW,), 'view=hot') is None


def test_typed_values_select_as_the_query_does():
    """A subcommand's typed values (its argparse dests, unset ones None or False) select as the URI query does."""
    assert selected_cap(DECLARATIONS, {'ranking': True, 'view': None}) == 'top'
    assert selected_cap(DECLARATIONS, {'rank_legacy': 'yes'}) == 'top'
    assert selected_cap(DECLARATIONS, {'ranking': False, 'view': 'hot'}) is None
    assert selected_cap(DECLARATIONS, {}) is None
