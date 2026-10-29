"""Fresh command hints must vary only by the qualified temporary corpus root."""
from urllib.parse import quote

import pytest

from scripts.check_parse_counts import _normalize_result


@pytest.mark.parametrize('form', ['path', 'uri', 'encoded_uri'])
def test_command_corpus_prefix_normalizes_without_losing_query_or_flags(tmp_path, form):
    first, second = tmp_path / 'first space' / 'corpus', tmp_path / 'second space' / 'corpus'

    def answer(root):
        path = root.as_posix()
        if form == 'encoded_uri':
            path = quote(path, safe='/.:')
        command = (f"reveal check '{path}' --exclude '*.tmp'" if form == 'path'
                   else f"reveal 'imports://{path}?rank=fan-in&scope=path' --no-gitignore")
        return {'next_steps': [{'command': command}], 'path': str(root),
                'note': 'keep this literal value', 'total': 3}

    normalized = _normalize_result(answer(first), first)
    assert normalized == _normalize_result(answer(second), second)
    assert '<corpus>' in normalized['next_steps'][0]['command']
    assert normalized['total'] == 3 and normalized['note'] == 'keep this literal value'
    assert normalized['next_steps'][0]['command'].endswith(
        "--exclude '*.tmp'" if form == 'path' else '--no-gitignore')


def test_normalization_does_not_rewrite_arbitrary_text_or_a_sibling_prefix(tmp_path):
    corpus = tmp_path / 'corpus'
    text = f'reveal {corpus}'
    source = {'note': text, 'command': f'reveal {corpus}-other --check'}
    assert _normalize_result(source, corpus) == source
