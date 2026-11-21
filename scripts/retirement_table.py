#!/usr/bin/env python3
"""The old-to-new table of every retired spelling, generated from the declarations (BACK-2716 step 4).

The cut release's CHANGELOG carries this table (plan: "Its CHANGELOG entry carries the old-to-new table generated from
RETIREMENTS"). Three sources, each a generated list, never a hand table:

  table      every row of ``RETIREMENTS`` (reveal/cli/invocation.py): its old spelling, its replacement and its stage;
  generated  the shared-name family ``invocation.generated_retirements`` builds from the nouns' declarations;
  request    D20's request family: on every noun whose URI request says the one request note (``request_noted``), the
             analysis-only scheme itself and each declared query key, with the flag that replaces it, read by the same
             lookup the note's renderer uses (``canonical.spec_flag``). A key no flag spells yet says so: it keeps its own
             row's note (a standalone legacy word) or waits on its noun's package.

Usage: python scripts/retirement_table.py [--format markdown|json]
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reveal.cli.invocation import (COMMANDS, REQUEST_STAGE, RETIREMENTS, generated_retirements,  # noqa: E402
                                   request_noted)

NO_FLAG_OWN_ROW = 'no flag: the request keeps this spelling\'s own note ({key})'
NO_FLAG_YET = 'no flag yet: the request says no note until its noun declares one'


def _row(kind: str, key: str, old: str, replacement: str, stage: str) -> Dict[str, str]:
    return {'kind': kind, 'key': key, 'old': old, 'replacement': replacement, 'stage': stage}


def _request_rows(noun: str) -> List[Dict[str, str]]:
    """The scheme row (an analysis-only scheme) and one row per declared query key of *noun*."""
    from reveal.adapters.base import get_adapter_class
    from reveal.cli.routing.canonical import spec_flag
    from reveal.cli.routing.declared import create_declared_parser, declared_adapter_class
    adapter, parser = declared_adapter_class(noun), create_declared_parser(noun)
    analysis_only = getattr(get_adapter_class(noun), 'ANALYSIS_ONLY', False)
    target = 'PATH' if analysis_only else 'RESOURCE'
    command = f'reveal {noun} PATH' if analysis_only else f'reveal {noun}://RESOURCE'
    rows = []
    if analysis_only:
        rows.append(_row('request', f'request:{noun}', f'{noun}://PATH', command, REQUEST_STAGE))
    for spec in adapter.PARAM_SPECS:
        if spec.flag_only:
            continue
        flag = spec_flag(spec, parser, adapter)
        action = parser._option_string_actions.get(flag) if flag else None
        value = 'V'
        if action is not None and action.nargs == 0:  # a switch: given true, or (a store_false flag) given false
            value = 'false' if action.const is False else 'true'
        old = f'{noun}://{target}?{spec.name}={value}'
        if flag is None:
            own = f'param:{noun}.{spec.name}'
            replacement = NO_FLAG_OWN_ROW.format(key=own) if own in RETIREMENTS else NO_FLAG_YET
        else:
            replacement = f'{command} {flag}' + ('' if action is not None and action.nargs == 0 else ' V')
        rows.append(_row('request', f'request:{noun}.{spec.name}', old, replacement, REQUEST_STAGE))
    return rows


def migration_rows() -> List[Dict[str, str]]:
    """Every retired spelling: the table, the generated family and the request family, in that order."""
    rows = [_row('table', key, entry.old, entry.replacement, entry.stage) for key, entry in RETIREMENTS.items()]
    rows += [_row('generated', key, entry.old, entry.replacement, entry.stage)
             for key, entry in generated_retirements().items() if key not in RETIREMENTS]  # a table row wins
    for noun in sorted(COMMANDS):
        if request_noted(noun):
            rows += _request_rows(noun)
    return rows


def _cell(text: str) -> str:
    return '`' + text.replace('|', '\\|') + '`' if text and not text.startswith('no flag') else text.replace('|', '\\|')


def markdown(rows: List[Dict[str, str]]) -> str:
    lines = ['| Old spelling | Use instead | Stage |', '|---|---|---|']
    lines += [f"| {_cell(row['old'])} | {_cell(row['replacement'])} | {row['stage']} |" for row in rows]
    return '\n'.join(lines) + '\n'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n', 1)[0])
    parser.add_argument('--format', choices=('markdown', 'json'), default='markdown')
    args = parser.parse_args(argv)
    rows = migration_rows()
    sys.stdout.write(json.dumps(rows, indent=2) + '\n' if args.format == 'json' else markdown(rows))
    return 0


if __name__ == '__main__':
    sys.exit(main())
