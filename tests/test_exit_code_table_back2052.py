"""One exit-code table, rendered into every D6 command's help (BACK-2051 slice 5, BACK-2052).

The words live in cli/invocation.py (EXIT_CODES, EXIT_CODE_WORDING) beside COMMANDS; a command's
--help derives from them and from the --fail-on values its owner declares, so help cannot
promise an exit 1 that the command can never produce.
"""
import os
import subprocess
import sys

import pytest

from reveal.cli.invocation import (COMMANDS, EXIT_CODES, EXIT_CODE_WORDING, LEGACY_CLI_MODIFIERS, RETIREMENTS,
                                   exit_codes_text)
from reveal.cli.routing.declared import declared_adapter_class

_DECLARED = sorted(n for n, spec in COMMANDS.items() if spec.declared_adapter)
_FILE_COMMANDS = ('check', 'review', 'health')


def _help(command):
    env = {**os.environ, 'COLUMNS': '300'}
    return subprocess.run([sys.executable, '-m', 'reveal', command, '--help'], capture_output=True,
                          text=True, env=env, timeout=60, check=False, encoding='utf-8').stdout


def test_retirement_inventory_matches_the_shipped_migrations():
    """Keep the inventory explicit; each migration is exercised in its owning tests.

    BACK-2377 adds architecture aliases; BACK-2364 adds contextual navigation corrections;
    BACK-2461 adds the three effects replacement notes. BACK-2225 adds python://, removed outright.
    BACK-2149 adds the hotspots noun and its two only-flags. BACK-2620 adds the four Imports aliases.
    BACK-2621 adds the ten Metrics legacy spellings. BACK-2654 adds the different words AST type and Markdown
    body-contains and fields, AST's bare depth (rule 8) the four presentation switches' --no-NAME and --no-gitignore (rule 15).
    BACK-2673 adds Hotspots' and Testability's top and the main-parser flags declared nouns keep (LEGACY_CLI_MODIFIERS).
    BACK-2622 adds Overview's top (a standalone legacy cap) and no_imports (--imports off).
    BACK-2725 adds JSON's data-only (a standalone legacy setting: the bare lines array).
    BACK-2616 adds Git's type, no_merges and raw (--view, --merges off, --detail raw) and its view=log and
    detail=summary values (--view history, --detail normal). BACK-2626 adds SQLite's check (--view health). BACK-2752 adds env's show_secrets, removed outright. BACK-2614 adds
    Markdown's link-graph and lint (--view links, --view lint) and its standalone aggregate (--view aggregate --field FIELD).
    BACK-2627 adds the element view flags --boundary, --effects, --flow and --exits (--view).
    BACK-2733 adds Git's ignore (--ignore-commits SHAS, or --auto-ignore off for ignore=off).
    BACK-2767 adds the positional element of help:// and reveal:// (help://TOPIC, the path read of a source file).
    BACK-2774 adds the pressure report's and Testability's tests (--test-paths PATHS; --tests is the shared policy).
    BACK-2773 adds help's search and top (--match TEXT, --limit N) and the search term in the path (help://search/TERM).
    """
    generated = [f'flag:{noun}.{flag}' for noun, flags in LEGACY_CLI_MODIFIERS.items() for flag in flags]  # BACK-2673
    assert sorted(RETIREMENTS) == sorted(generated + ['flag:--also-json', 'flag:--boundary', 'flag:--calls', 'flag:--catchmap', 'flag:--check', 'flag:--deps',
                                   'flag:--effects', 'flag:--exits', 'flag:--fanout', 'flag:--flow', 'flag:--flowto', 'flag:--ifmap', 'flag:--loopmap', 'flag:--mutations',
                                   'flag:--no-breadcrumbs', 'flag:--no-fallback', 'flag:--no-gitignore', 'flag:--no-group', 'flag:--no-snippets',
                                   'flag:--returns', 'flag:--search', 'flag:--sideeffects', 'flag:--statewrites',
                                   'flag:--verbose', 'flag:--writes', 'param:architecture.verbose', 'param:ast.callee_of', 'param:ast.calls', 'param:ast.depth', 'param:ast.show', 'param:ast.type',
                                   'param:calls.external', 'param:calls.modules', 'param:calls.rank', 'param:calls.root', 'param:calls.target', 'param:calls.top', 'param:calls.type', 'param:calls.uncalled',
                                   'param:contracts.impls', 'param:patches.group', 'param:patches.min_categories', 'param:patches.min_patches', 'param:patches.no_suppress', 'param:patches.tests', 'param:patches.top', 'param:contracts.no_implementations', 'param:sqlite.check', 'param:xlsx.range', 'param:xlsx.search', 'param:env.show_secrets', 'param:help.search', 'param:help.top', 'param:surface.by', 'param:surface.depth', 'param:surface.source_only', 'param:surface.top', 'param:surface.type', 'param:claude.contains', 'param:claude.filter', 'param:claude.full', 'param:claude.last', 'param:claude.raw', 'param:claude.search', 'param:claude.summary', 'param:claude.tail',
                                   'param:codex.filter', 'param:codex.full', 'param:codex.goal', 'param:codex.last', 'param:codex.search', 'param:codex.tokens',
                                   'param:deps.verbose', 'param:git.ignore', 'param:git.no_merges', 'param:git.raw', 'param:git.type', 'param:git.verbose',
                                   'param:json.data-only', 'param:json.flatten', 'param:json.gron', 'param:json.keys', 'param:json.length', 'param:json.schema', 'param:json.type',
                                   'param:hotspots.files_only', 'param:hotspots.functions_only', 'param:hotspots.verbose',
                                   'param:imports.max_files', 'param:imports.rank', 'param:imports.top', 'param:imports.verbose',
                                   'param:markdown.aggregate', 'param:markdown.body-contains', 'param:markdown.fields', 'param:markdown.link-graph',
                                    'param:markdown.lint',
                                   'param:metrics.hotspots', 'param:metrics.max_complexity', 'param:metrics.max_lines',
                                   'param:metrics.min_complexity', 'param:metrics.min_functions', 'param:metrics.min_lines',
                                   'param:metrics.no_churn', 'param:metrics.no_merges', 'param:metrics.summary_only',
                                   'param:metrics.top', 'param:overview.no_imports', 'param:overview.top', 'param:overview.verbose', 'param:pack.verbose',
                                   'param:testability.tests', 'param:testability.verbose', 'scheme:architecture', 'scheme:classify', 'scheme:depends', 'scheme:deps', 'scheme:hotspots', 'scheme:python', 'scheme:stats', 'scheme:testability', 'scheme:trace', 'subcommand:architecture', 'subcommand:deps', 'subcommand:hotspots', 'subcommand:review', 'subcommand:scaffold', 'subcommand:testability',
                                   'subcommand:trace', 'target:diff.element', 'target:health.code', 'target:help.element', 'target:help.search-term', 'target:nav.outline',
                                   'target:reveal.element', 'value:ast.show=calls', 'value:ast.view=calls',
                                   'value:calls.detail=false', 'value:calls.detail=true',
                                    'value:git.detail=summary', 'value:git.view=log',
                                   'param:hotspots.top', 'param:testability.top'])


def test_table_covers_the_four_codes_and_commands_only_reword_them():
    assert sorted(EXIT_CODES) == [0, 1, 2, 3]
    for command, wording in EXIT_CODE_WORDING.items():
        assert command in COMMANDS and set(wording) <= set(EXIT_CODES)


def test_a_command_without_a_findings_gate_never_documents_exit_1():
    text = exit_codes_text('pack', ('none',))
    assert '  1  ' not in text and '--fail-on none reports' not in text
    assert '  1  ' in exit_codes_text('deps', ('none', 'findings'))


@pytest.mark.parametrize('command', _FILE_COMMANDS)
def test_file_commands_print_the_table(command):
    out = _help(command)
    for line in exit_codes_text(command).splitlines():
        assert line.strip() in out, (command, line)
    # Negative control: another command's wording is not in this help.
    assert exit_codes_text('health') not in _help('check')


@pytest.mark.parametrize('name', _DECLARED)
def test_declared_command_help_matches_its_declared_gates(name):
    gates = getattr(declared_adapter_class(name), 'FINDINGS_POLICIES', ('none',))
    out = _help(name)
    for line in exit_codes_text(name, gates).splitlines():
        assert line.strip() in out, (name, line)
    assert ('1  ' in out.split('Exit codes:')[1].split('\n\n')[0]) == ('findings' in gates)
