"""Explicit imports must not manufacture an ancestor through an unrelated same-named function."""
from pathlib import Path

from reveal.api import query


def tree(root, name='run'):
    (root / 'a.py').write_text('def sink(): return 1\ndef run(): return sink()\n', encoding='utf-8')
    (root / 'b.py').write_text(f'def {name}(): return 2\n', encoding='utf-8')
    (root / 'top.py').write_text(f'from b import {name}\ndef top(): return {name}()\n', encoding='utf-8')


def reverse(root, target='sink', depth=2):
    return query(f'calls://{root.as_posix()}?callers={target}&depth={depth}')


def names(answer):
    return [(level['level'], Path(row['file']).name, row['caller'])
            for level in answer['levels'] for row in level['callers']]


def test_rename_of_unrelated_definition_does_not_move_sink_chain(tmp_path):
    tree(tmp_path)
    before = names(reverse(tmp_path))
    assert before == [(1, 'a.py', 'run')]
    tree(tmp_path, 'other_run')
    assert names(reverse(tmp_path)) == before


def test_real_import_chain_agrees_with_forward_target(tmp_path):
    tree(tmp_path)
    (tmp_path / 'top.py').write_text('from a import run as entry\ndef top(): return entry()\n', encoding='utf-8')
    answer = reverse(tmp_path)
    assert names(answer) == [(1, 'a.py', 'run'), (2, 'top.py', 'top')]
    forward = query(f'calls://{tmp_path.as_posix()}?callees=top&depth=2')
    target = forward['levels'][0]['callees'][0]
    record = answer['levels'][1]['callers'][0]
    assert record['target_resolution'] == 'resolved'
    assert (record['target_file'], record['target_line']) == (target['callee_file'], target['callee_line'])


def test_ambiguous_candidates_remain_explicit_candidates(tmp_path):
    tree(tmp_path)
    (tmp_path / 'top.py').write_text('def top(): return run()\n', encoding='utf-8')
    answer = reverse(tmp_path)
    assert names(answer) == [(1, 'a.py', 'run'), (2, 'top.py', 'top')]
    record = answer['levels'][1]['callers'][0]
    assert record['target_resolution'] == 'ambiguous'
    assert {Path(c['file']).name for c in record['target_candidates']} == {'a.py', 'b.py'}


def test_name_only_external_and_depth_one_queries_keep_their_population(tmp_path):
    (tmp_path / 'a.py').write_text('def f(): return external()\n', encoding='utf-8')
    assert names(reverse(tmp_path, 'external', 1)) == [(1, 'a.py', 'f')]
    assert names(reverse(tmp_path, 'external', 2)) == [(1, 'a.py', 'f')]


def test_qualified_import_proof_and_repeated_request_edit(tmp_path):
    tree(tmp_path)
    (tmp_path / 'top.py').write_text('import b as other\ndef top(): return other.run()\n', encoding='utf-8')
    assert names(reverse(tmp_path)) == [(1, 'a.py', 'run')]
    (tmp_path / 'top.py').write_text('import a as other\ndef top(): return other.run()\n', encoding='utf-8')
    assert names(reverse(tmp_path)) == [(1, 'a.py', 'run'), (2, 'top.py', 'top')]
    # Root name matching is an unchanged query policy, independent of later-hop identity.
    assert names(reverse(tmp_path, 'Fake.sink')) == names(reverse(tmp_path))


def test_typescript_import_distinguishes_later_definition(tmp_path):
    (tmp_path / 'a.ts').write_text('export function sink() {}\nexport function run() { sink(); }\n', encoding='utf-8')
    (tmp_path / 'b.ts').write_text('export function run() {}\n', encoding='utf-8')
    (tmp_path / 'top.ts').write_text('import { run } from "./b";\nexport function top() { run(); }\n', encoding='utf-8')
    assert names(reverse(tmp_path)) == [(1, 'a.ts', 'run')]


def test_member_name_candidates_keep_the_disclosed_policy(tmp_path):
    (tmp_path / 'a.cs').write_text('namespace P { class A { public static void sink() {} public static void run() { sink(); } } }\n', encoding='utf-8')
    (tmp_path / 'b.cs').write_text('namespace P { class B { public static void run() {} } }\n', encoding='utf-8')
    (tmp_path / 'top.cs').write_text('using Other = P.B;\nnamespace P { class Top { public static void top() { Other.run(); } } }\n', encoding='utf-8')
    answer = reverse(tmp_path)
    assert any(row['caller'].endswith('top') for level in answer['levels'] for row in level['callers'])
    assert answer['levels'][1]['callers'][0]['target_resolution'] in ('ambiguous', 'name_only')
