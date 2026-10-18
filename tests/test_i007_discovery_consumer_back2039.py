"""Exact manifest scope and normal host lifetime for I007 evidence loss (BACK-2039)."""
import os
import sys
import time
from pathlib import Path

import pytest

from reveal.rules.imports import _dep_reconciliation as dep
from reveal.rules.imports.I007 import I007
from reveal.rules.scan_caches import get_scan_disclosures
from reveal.utils.request_cache import request_started_ns, reset_request_caches, seal_request_caches


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    aged = time.time_ns() - 60_000_000_000
    os.utime(path, ns=(aged, aged))
    return path


@pytest.fixture
def project(tmp_path):
    py = write(tmp_path / 'pyproject.toml', '[project]\nname="mixed"\ndependencies=["requests", "orjson"]\n')
    rs = write(tmp_path / 'Cargo.toml', '[package]\nname="mixed"\nversion="0.1.0"\n[dependencies]\nserde="1"\nrand="0.8"\n')
    write(tmp_path / 'visible.py', 'import orjson\n')
    write(tmp_path / 'visible.rs', 'use rand::Rng;\nfn visible() {}\n')
    write(tmp_path / 'py_hidden' / 'usage.py', 'import requests\n')
    write(tmp_path / 'rs_hidden' / 'usage.rs', 'use serde::Serialize;\nfn hidden() {}\n')
    return {'.py': py, '.rs': rs}


class Denial:
    """Deny actual scandir only while the native analytical index is building."""
    def __init__(self, monkeypatch, root, language, unknown=False):
        self.active = None
        self.enabled = True
        self.language = language
        self.unknown = unknown
        self.events = []
        self.builds = []
        real_scan = dep._scan_project_imports_uncached
        real_scandir = os.scandir
        hidden = root / ('py_hidden' if language == '.py' else 'rs_hidden')

        def scan(root, extensions, normalize, sep, *args, **kwargs):
            prior = self.active
            self.active = next(iter(extensions))
            self.builds.append(self.active)
            try:
                return real_scan(root, extensions, normalize, sep, *args, **kwargs)
            finally:
                self.active = prior

        def scandir(path):
            if self.enabled and self.active == language and Path(path) == hidden:
                self.events.append(str(hidden))
                if self.unknown:
                    raise PermissionError('independent unnamed evidence denial')
                raise PermissionError(13, 'independent evidence denial', str(hidden))
            return real_scandir(path)

        monkeypatch.setattr(dep, '_scan_project_imports_uncached', scan)
        monkeypatch.setattr(os, 'scandir', scandir)


def check(manifest):
    rule = I007()
    findings = rule.check(str(manifest), None, '')
    return findings, rule


def request(call):
    started = request_started_ns()
    reset_request_caches()
    try:
        return call()
    finally:
        seal_request_caches(started)


@pytest.mark.parametrize('language', ['.py', '.rs'])
@pytest.mark.parametrize('unknown', [False, True])
def test_disclosure_selects_checked_manifest_exact_language_key(project, monkeypatch, language, unknown):
    manifest = project[language]
    fault = Denial(monkeypatch, manifest.parent, language, unknown)
    findings, rule = check(manifest)
    other = project['.rs' if language == '.py' else '.py']
    assert check(other)[0] == []
    assert fault.events and len(findings) == 1
    assert len(dep._scan_cache[manifest.parent]) == 2
    # A healthy sibling language/root, ignored rule and absent checked population
    # cannot acquire this key's missing evidence, nor trigger another scan.
    before = list(fault.builds)
    for files, select, ignore in [([other], ['I007'], None), (None, ['I007'], None),
                                ([], ['I007'], None), ([manifest], ['I007'], ['I007']),
                                ([manifest.parent / 'visible.py'], ['I007'], None)]:
        assert get_scan_disclosures(files, select, ignore) == []
    assert fault.builds == before
    notes = get_scan_disclosures([manifest, manifest], ['I007'], None)
    assert len(notes) == 1, 'actual I007 evidence loss must reach selected public Check notes'
    assert 'I007' in notes[0] and 'director' in notes[0].lower()
    assert 'unused' in notes[0].lower() and ('may' in notes[0].lower() or 'false' in notes[0].lower())
    assert rule.outcomes and rule.outcomes[-1]['status'] == 'unavailable'
    if unknown:
        assert '0 identified directory' in notes[0]
        assert '1 enumeration error event(s)' in notes[0]
        assert 'independent unnamed evidence denial' in notes[0]


@pytest.mark.parametrize('language', ['.py', '.rs'])
def test_partial_second_key_in_already_stamped_root_recovers_without_manual_clear(project, monkeypatch, language):
    manifest = project[language]
    other = project['.rs' if language == '.py' else '.py']
    fault = Denial(monkeypatch, manifest.parent, language)
    assert request(lambda: check(other)[0]) == []
    # The root is already stamped through its healthy language key before loss.
    assert len(dep._scan_cache[manifest.parent]) == 1
    assert len(request(lambda: check(manifest)[0])) == 1
    assert fault.events
    first_events = len(fault.events)
    assert len(request(lambda: check(manifest)[0])) == 1
    assert len(fault.events) > first_events, 'partial key must rebuild at the next normal host reset'
    fault.enabled = False
    assert request(lambda: check(manifest)[0]) == [], 'repair must remove the false unused finding'
    built = list(fault.builds)
    assert request(lambda: check(manifest)[0]) == []
    assert fault.builds == built, 'healthy repaired evidence must retain validated-cache reuse'
    sibling = write(manifest.parent.parent / 'sibling' / 'requirements.txt', 'requests\n')
    write(sibling.parent / 'app.py', 'import requests\n')
    assert request(lambda: check(sibling)[0]) == []


@pytest.mark.parametrize('language', ['.py', '.rs'])
@pytest.mark.parametrize('fmt', ['text', 'json'])
def test_legacy_manifest_cli_qualifies_false_unused_evidence(project, monkeypatch, capsys, language, fmt):
    from reveal.main import main
    manifest = project[language]
    fault = Denial(monkeypatch, manifest.parent, language)
    monkeypatch.setattr(sys, 'argv', ['reveal', str(manifest), '--check', '--select', 'I007', '--format', fmt])
    try:
        code = main()
    except SystemExit as error:
        code = error.code
    output = capsys.readouterr()
    assert fault.events, 'fault must reach actual analytical enumeration'
    assert code == 3, 'incomplete evidence takes precedence over a false unused finding'
    combined = output.out + output.err
    assert 'I007' in combined and 'director' in combined.lower()
    assert 'unused' in combined.lower() and ('may' in combined.lower() or 'false' in combined.lower())


@pytest.mark.parametrize('language', ['.py', '.rs'])
def test_zero_declarations_do_not_disclose_an_old_same_invocation_partial_key(project, monkeypatch, language):
    manifest = project[language]
    fault = Denial(monkeypatch, manifest.parent, language)
    assert len(check(manifest)[0]) == 1 and fault.events
    write(manifest, '[project]\nname="empty"\n' if language == '.py' else '[package]\nname="empty"\nversion="0.1.0"\n')
    before = list(fault.builds)
    assert check(manifest)[0] == []
    assert get_scan_disclosures([manifest], ['I007'], None) == []
    assert fault.builds == before


def test_existing_pair_protocol_and_disclosure_miss_are_unchanged(tmp_path, monkeypatch):
    pair = dep.ProjectImports(frozenset({'x'}), ('bad.py',))
    names, skipped = pair
    assert len(pair) == 2 and names == {'x'} and skipped == ('bad.py',)
    assert tuple(dep.DeclaredUnused(frozenset(), ())) == (frozenset(), ())
    manifest = write(tmp_path / 'requirements.txt', 'requests\n')
    calls = []
    monkeypatch.setattr(dep, '_scan_project_imports_uncached', lambda *a, **k: calls.append(1))
    assert get_scan_disclosures([manifest], ['I007'], None) == []
    assert calls == [], 'collecting disclosures must never create an unrequested index'
