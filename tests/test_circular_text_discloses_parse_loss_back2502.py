"""``imports://DIR?circular`` text says the graph is incomplete and names the files that failed (BACK-2502).

With a sibling that failed to parse, ``?circular`` exited 3 and its JSON listed ``files_failed``, but
the text printed "✅ No circular dependencies found!" and named no file: the green line the BACK-1245
class was about. The base ``imports://`` view already listed the failed files; both now print the
same block.
"""
from conftest import _run_reveal_direct


def write(root, files):
    for name, text in files.items():
        (root / name).write_bytes(text.encode('utf-8'))


def circular(root):
    return _run_reveal_direct(f'imports://{root.as_posix()}?circular')


def test_no_cycles_beside_a_broken_file_is_not_a_green_verdict(tmp_path):
    write(tmp_path, {'a.ts': 'import { b } from "./b";\nexport const a = 1;\n',
                     'b.ts': 'export const b = 2;\n',
                     'bad.ts': 'export const = ;\nimport {\n'})
    result = circular(tmp_path)
    assert result.returncode == 3, (result.stdout, result.stderr)
    assert 'No circular dependencies found' not in result.stdout
    assert 'analysis is incomplete' in result.stdout
    assert '- bad.ts' in result.stdout and 'parsed with errors' in result.stdout


def test_a_cycle_beside_a_broken_file_names_the_file_too(tmp_path):
    write(tmp_path, {'a.ts': 'import { b } from "./b";\nexport const a = 1;\n',
                     'b.ts': 'import { a } from "./a";\nexport const b = 2;\n',
                     'bad.ts': 'export const = ;\nimport {\n'})
    result = circular(tmp_path)
    assert 'Circular Dependencies: 1 cycle group' in result.stdout
    assert '- bad.ts' in result.stdout, result.stdout


def test_a_clean_acyclic_directory_keeps_its_green_line(tmp_path):
    write(tmp_path, {'a.ts': 'import { b } from "./b";\nexport const a = 1;\n',
                     'b.ts': 'export const b = 2;\n'})
    result = circular(tmp_path)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert '✅ No circular dependencies found!' in result.stdout
    assert 'parsed with errors' not in result.stdout


def test_the_base_view_still_lists_the_failed_file(tmp_path):
    write(tmp_path, {'a.ts': 'export const a = 1;\n', 'bad.ts': 'export const = ;\nimport {\n'})
    result = _run_reveal_direct(f'imports://{tmp_path.as_posix()}')
    assert 'parsed with errors' in result.stdout and '- bad.ts' in result.stdout, result.stdout
