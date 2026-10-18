"""Returned contracts text; shared emission owns format and diagnostics."""
from functools import partial
from typing import Any, Dict, List

from ..base import BaseRenderer, capped_section
from ...adapters.surface import _unparsed_note
from ...utils.warning_render import meta_warning_lines

_LANGUAGE_LABELS: Dict[str, str] = {
    'python': 'Python',
    'ts': 'TypeScript / Java / C# / PHP / Swift / Kotlin / JS',
    'ruby': 'Ruby',
    'go': 'Go',
    'rust': 'Rust',
    'cpp': 'C++',
}

# Fixed render order for the polyglot (`by_language`) case — arbitrary but stable.
_LANGUAGE_RENDER_ORDER: List[str] = ['python', 'ts', 'ruby', 'go', 'rust', 'cpp']

def _render_contract_groups(mode: str, report: Dict[str, Any], impls_cap: int = 5) -> List[str]:
    """Render one language's contract groups under its own labels/groupings."""
    lines: List[str] = []
    group = partial(_render_group, impls_cap=impls_cap)
    if mode == 'ts':
        lines += group("Abstract Classes", report['abcs'], show_methods=False, show_impls=True)
        lines += group("Interfaces", report['protocols'], show_methods=False, show_impls=True)
        lines += group("Type Aliases", report['typeddicts'], show_methods=False, show_impls=False)
        lines += group("Implementing Classes", report['dataclasses'], show_methods=False, show_impls=False)
    elif mode == 'ruby':
        lines += group("Mixins (Modules)", report['protocols'], show_methods=False, show_impls=True)
        lines += group("Including Classes", report['dataclasses'], show_methods=False, show_impls=False)
    elif mode == 'go':
        lines += group("Interfaces", report['protocols'], show_methods=False, show_impls=True)
        lines += group("Implementing Types (structural)", report['dataclasses'], show_methods=False, show_impls=False)
    elif mode == 'rust':
        lines += group("Traits", report['protocols'], show_methods=False, show_impls=True)
        lines += group("Implementing Types", report['dataclasses'], show_methods=False, show_impls=False)
    elif mode == 'cpp':
        lines += group("Abstract Classes (interfaces)", report['protocols'], show_methods=False, show_impls=True)
        lines += group("Subclasses", report['dataclasses'], show_methods=False, show_impls=False)
    else:
        lines += group("Abstract Base Classes", report['abcs'], show_methods=True, show_impls=True)
        lines += group("Protocols", report['protocols'], show_methods=True, show_impls=True)
        lines += group("TypedDicts", report['typeddicts'], show_methods=False, show_impls=False)
        lines += group("Dataclasses", report['dataclasses'], show_methods=False, show_impls=False)
        lines += group("Pydantic BaseModels", report['basemodels'], show_methods=False, show_impls=False)
        lines += group("Path-heuristic bases", report['path_heuristic'], show_methods=True, show_impls=True)

    return lines

def _has_contract_rows(report: Dict[str, Any]) -> bool:
    return any(report.get(key) for key in (
        'abcs', 'protocols', 'typeddicts', 'dataclasses', 'basemodels', 'path_heuristic'))


def _no_contracts_hint(mode: str) -> str:
    if mode == 'ts':
        return "  Try widening the path or checking for interface/abstract class usage."
    if mode == 'ruby':
        return "  Try widening the path or checking for module/include/extend (mixin) usage."
    if mode == 'go':
        return "  Try widening the path or checking for interface type declarations."
    if mode == 'rust':
        return "  Try widening the path or checking for trait / impl-for declarations."
    if mode == 'cpp':
        return "  Try widening the path or checking for abstract classes (pure virtual methods)."
    return "  Try widening the path or checking imports for ABC/Protocol usage."


def _render_report(report: Dict[str, Any], impls_cap: int = 5) -> List[str]:
    lines: List[str] = []
    path = report['path']
    total = report['total_contracts']

    lines.append('')
    lines.append(f"Contracts: {path}")
    lines.append("━" * 50)
    # BACK-518: warn when reveal only understood a minority of the tree — the
    # results (total>0) are a supported-language subset, or the emptiness
    # (total==0) is a false-clean on a mostly-unsupported repo (e.g. 15 stray
    # .py files in a Lua tree yielding "no contracts"), not a real verdict. The
    # coverage warning supersedes the legacy detect_non_python_language decline.
    warning = report.get('coverage', {}).get('warning', '')
    notices = [warning] if warning else []
    if report.get('unparsed_files'):  # BACK-1588: a file with no grammar is not a clean file
        notices.append(f"⚠ {_unparsed_note(report['unparsed_files'])}")
    for notice in notices:
        lines.append(notice)
        lines.append('')
    lines.append(f"Total contracts found: {total}")
    lines.append('')

    by_language = report.get('by_language')
    if by_language is not None:
        # BACK-780: more than one language present — render each language's
        # section under its own labels rather than picking one winner.
        if not any(_has_contract_rows(group) for group in by_language.values()):
            if not warning:
                lines.append("  No contracts or seams found.")
                lines.append('')
            return lines
        for name in _LANGUAGE_RENDER_ORDER:
            group = by_language.get(name)
            if group is None:
                continue
            lines.append(f"── {_LANGUAGE_LABELS[name]} ──")
            lines.append('')
            lines += _render_contract_groups(name, group, impls_cap)
        return lines

    ts_mode = report.get('_ts_mode', False)
    ruby_mode = report.get('_ruby_mode', False)
    go_mode = report.get('_go_mode', False)
    rust_mode = report.get('_rust_mode', False)
    cpp_mode = report.get('_cpp_mode', False)
    mode = ('ts' if ts_mode else 'ruby' if ruby_mode else 'go' if go_mode
            else 'rust' if rust_mode else 'cpp' if cpp_mode else 'python')

    if not _has_contract_rows(report):
        if not warning:
            lang = report.get('unsupported_language', '')
            if lang:
                lines.append("  reveal contracts currently supports Python, TypeScript, JavaScript, Java, C#, PHP, Swift, Kotlin, Ruby, Go, Rust, and C++.")
                lines.append(f"  No supported files found — detected {lang}.")
            else:
                lines.append("  No contracts or seams found.")
                lines.append(_no_contracts_hint(mode))
            lines.append('')
        return lines

    lines += _render_contract_groups(mode, report, impls_cap)
    return lines


def _render_group(
    label: str,
    entries: List[Dict[str, Any]],
    show_methods: bool,
    show_impls: bool,
    impls_cap: int = 5,
) -> List[str]:
    lines: List[str] = []
    if not entries:
        return lines
    lines.append(f"{label} ({len(entries)}):")
    for cls in entries:
        name = cls['name']
        file_path = cls['file']
        line = cls['line']
        bases = cls.get('bases', [])
        bases_str = f"({', '.join(bases)})" if bases else ''
        lines.append(f"  {name}  {bases_str}  {file_path}:{line}")
        if show_methods and cls.get('abstract_methods'):
            methods = ', '.join(cls['abstract_methods'])
            lines.append(f"    → abstract: {methods}")
        if show_impls and cls.get('implementations'):
            impls = cls['implementations']
            impl_lines = capped_section(
                impls, impls_cap or None,
                lambda item: f"{item['name']} ({item['file']}:{item['line']})",
                indent="    ← ", suffix=" (?impls=0 lists all, ?impls=N widens)")
            footer = impl_lines.pop() if impls_cap and len(impls) > impls_cap else None
            lines.append(f"    ← implements: {', '.join(impl_lines)}")
            if footer:
                lines.append(footer.replace("...", "…", 1))
    lines.append('')
    return lines


def contracts_text(report: Dict[str, Any]) -> str:
    return "\n".join(_render_report(report, report.get('impls_cap', 5))) + "\n"


class ContractsRenderer(BaseRenderer):
    """Contract inventory renderer with a pure text body."""

    RENDERS_META_WARNINGS = True

    @classmethod
    def _render_text(cls, result: dict) -> str:
        # Coverage and unparsed-source notices retain their established place
        # above the inventory. The shared warning owner renders everything else.
        meta = result.get('meta') or {}
        remaining = {**result, 'meta': {**meta, 'warnings': [
            warning for warning in meta.get('warnings', [])
            if warning.get('code') not in ('W-CONTRACTS-1', 'W-CONTRACTS-2')]}}
        diagnostics = meta_warning_lines(remaining)
        return contracts_text(result) + ('\n'.join(diagnostics) + '\n' if diagnostics else '')
