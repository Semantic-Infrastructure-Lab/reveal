"""BACK-1488: three small CLI-message defects split off BACK-1422.

- surface:// on one file printed locations as '.:N'
- imports:// on a directory holding a single file claimed a 'single-file scan'
- calls:// with a bare name flag ('?callees') crashed with a str+bool TypeError
"""
import subprocess
import sys

SOURCE = "import os\n\n\ndef run():\n    return os.getcwd()\n"


def run_reveal(*args):
    return subprocess.run(
        [sys.executable, '-m', 'reveal.main'] + list(args),
        capture_output=True, text=True, encoding='utf-8',
    )


def test_surface_single_file_locations_name_the_file(tmp_path):
    f = tmp_path / "cli.py"
    f.write_text(
        "import argparse\n\n"
        "def main():\n"
        "    p = argparse.ArgumentParser()\n"
        "    p.add_argument('--verbose')\n",
        encoding='utf-8',
    )
    r = run_reveal(f"surface://{f}")
    assert r.returncode == 0, r.stderr
    assert "--verbose" in r.stdout
    assert "cli.py:5" in r.stdout
    assert ".:5" not in r.stdout.replace("cli.py:5", "")


def test_imports_single_file_directory_is_not_called_a_file_scan(tmp_path):
    (tmp_path / "only.py").write_text(SOURCE, encoding='utf-8')
    r = run_reveal(f"imports://{tmp_path}")
    assert r.returncode == 0, r.stderr
    assert "single-file scan" not in r.stdout
    assert "only one file scanned" in r.stdout


def test_imports_actual_single_file_keeps_single_file_message(tmp_path):
    f = tmp_path / "only.py"
    f.write_text(SOURCE, encoding='utf-8')
    r = run_reveal(f"imports://{f}")
    assert "single-file scan" in r.stdout


def test_calls_bare_name_flag_is_a_usage_error_not_a_crash(tmp_path):
    (tmp_path / "m.py").write_text("def bar():\n    return 1\n", encoding='utf-8')
    for query in ("target=bar&callees", "callees", "target", "root"):
        r = run_reveal(f"calls://{tmp_path}?{query}")
        combined = r.stdout + r.stderr
        assert "TypeError" not in combined and "concatenate" not in combined, query
        assert "startswith" not in combined, query
        assert "needs a function name" in combined, (query, combined)


def test_calls_named_callees_still_works(tmp_path):
    (tmp_path / "m.py").write_text("def bar():\n    return baz()\n\ndef baz():\n    return 1\n", encoding='utf-8')
    r = run_reveal(f"calls://{tmp_path}?callees=bar")
    assert r.returncode == 0, r.stderr
    assert "Callees of: bar" in r.stdout
