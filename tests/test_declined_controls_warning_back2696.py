"""``declined_controls_warning``: the given controls an answer that declined on the data never read (BACK-2696)."""
from reveal.utils.query_binding import bind_declared_params, declined_controls_warning
from reveal.utils.query_parser import ParamSpec, collect_query_keys

SPECS = (
    ParamSpec('view', 'string', 'answer', None, str, ('view=a',), choices=('a',), role='operation'),
    ParamSpec('limit', 'integer', 'cap', 20, int, ('limit=1',), minimum=0, role='presentation'),
    ParamSpec('since', 'string', 'bound', None, str, ('since=x',), role='analysis'),
    ParamSpec('min', 'integer', 'floor', 1, int, ('min=2',), minimum=0, role='analysis'),
)


def test_names_the_given_controls_the_answer_never_read_and_marks_them_used():
    with collect_query_keys(warnings_to_stderr=False) as log:
        params = bind_declared_params(SPECS, 'view=a&limit=0&since=x&min=2', transport='uri')
        params.get('since')  # read before the answer declined: it shaped the verdict
        warning = declined_controls_warning(SPECS, params)
        assert warning['code'] == 'control_unread_by_data'
        assert warning['fields'] == ['limit', 'min']  # declaration order; never the operation, never a read control
        assert "'limit', 'min' have no effect on this data" in warning['message']
        assert {'limit', 'min'} <= log.used  # the disclosure is their use: the ledger does not name them again


def test_nothing_to_name_when_no_control_was_given_or_every_one_was_read():
    with collect_query_keys(warnings_to_stderr=False):
        assert declined_controls_warning(SPECS, bind_declared_params(SPECS, 'view=a', transport='uri')) is None
        params = bind_declared_params(SPECS, 'limit=3', transport='uri')
        params.get('limit')
        assert declined_controls_warning(SPECS, params) is None


def test_outside_a_dispatch_that_records_reads_it_names_nothing():
    """Without a read log nothing can tell read from unread, and the ledger names nothing there either."""
    assert declined_controls_warning(SPECS, bind_declared_params(SPECS, 'limit=0', transport='uri')) is None


def test_an_undeclared_adapter_has_no_declarations_to_name():
    with collect_query_keys(warnings_to_stderr=False):
        assert declined_controls_warning((), bind_declared_params(SPECS, 'limit=0', transport='uri')) is None
