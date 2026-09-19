#!/usr/bin/env python3
"""Real-corpus sweeps that catch what fixture tests cannot.

On 2026-09-18 these sweeps found a BACK-1289 regression (Java/C#/Dart switch
complexity silently dropped) plus Java/Dart/Swift nav-call gaps while ~2,300
fixture tests stayed green. Run them before a release, or after touching
complexity / call extraction.

Two sweeps, both over a deterministic sample of ~/.cache/reveal-corpus
(materialize with scripts/fetch_corpus.py):

  agree       analyzer calls (get_structure) vs nav calls (range_calls) per
              function, compared as bare names. Reports Jaccard per language
              plus the top names seen by only one side. 1.0 = paths agree.
  complexity  per-function complexity for the current tree vs --base-ref
              (built via `git archive`, no stash, no checkout). Reports how
              many files/functions changed per language and examples.

Usage:
    python scripts/corpus_sweep.py agree                      # HEAD tree only
    python scripts/corpus_sweep.py agree --base-ref c577a14a  # before -> after
    python scripts/corpus_sweep.py complexity --base-ref HEAD~5 -n 100
    python scripts/corpus_sweep.py agree ruby java -o /tmp/agree.json
    python scripts/corpus_sweep.py agree --min-jaccard 0.98 --floor javascript=0.90   # pre-release gate

Sampling is seeded per sweep, so the same corpus + args always pick the same
files. Exits 0 with a message when the corpus is absent (never fails a
pre-release check just because the cache isn't populated).
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "node_modules", "vendor", "thirdparty"}
MIN_BYTES, MAX_BYTES = 500, 150_000

# language dir under the corpus -> (extensions, tree-sitter grammar)
LANGS = {
    "ruby": ((".rb",), "ruby"), "java": ((".java",), "java"), "dart": ((".dart",), "dart"),
    "go": ((".go",), "go"), "python": ((".py",), "python"), "php": ((".php",), "php"),
    "javascript": ((".js",), "javascript"), "typescript": ((".ts",), "typescript"),
    "rust": ((".rs",), "rust"), "csharp": ((".cs",), "csharp"), "kotlin": ((".kt",), "kotlin"),
    "swift": ((".swift",), "swift"), "scala": ((".scala",), "scala"),
    "cpp": ((".cpp", ".cc", ".h"), "cpp"), "c": ((".c",), "c"),
}
AGREE_SEED, COMPLEXITY_SEED = 7, 11


def corpus_dir() -> Path:
    return Path(os.environ.get("REVEAL_CORPUS_DIR", "~/.cache/reveal-corpus")).expanduser()


def sample_files(lang: str, n: int, seed: int) -> list[Path]:
    exts, _ = LANGS[lang]
    files = []
    for dp, dn, fn in os.walk(corpus_dir() / lang):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            p = Path(dp) / f
            if f.endswith(exts) and MIN_BYTES < p.stat().st_size < MAX_BYTES:
                files.append(p)
    files.sort()  # os.walk order is filesystem-dependent; shuffle from a stable base
    random.Random(seed).shuffle(files)
    return sorted(files[:n])


# --------------------------------------------------------------------------
# Worker side: runs against whichever reveal tree is on sys.path (--src).
# --------------------------------------------------------------------------

def _function_scopes(root, function_types, zero_arg, node_children):
    """Function nodes to feed nav; Dart signatures resolve to the sibling body's parent."""
    out, stack = [], [root]
    while stack:
        n = stack.pop()
        k = zero_arg(n, "kind")
        if k in function_types:
            scope = n
            if k == "function_signature":
                scope = zero_arg(n, "parent")
                while scope is not None and zero_arg(scope, "kind") == "method_signature":
                    scope = zero_arg(scope, "parent")
            out.append(scope)
        stack.extend(node_children(n))
    seen, uniq = set(), []
    for n in out:
        key = (zero_arg(n, "start_byte"), zero_arg(n, "end_byte"))
        if key not in seen:
            seen.add(key)
            uniq.append(n)
    return uniq


def worker_agree(langs: list[str], n: int, topn: int) -> dict:
    import tree_sitter_language_pack as ts
    from reveal.adapters.calls.index import _bare_callee_name
    from reveal.core import node_children
    from reveal.core.nav_calls import range_calls
    from reveal.core.node_taxonomy import FUNCTION_TYPES
    from reveal.core.treesitter_compat import _zero_arg, ts_parse, tree_root
    from reveal.registry import get_analyzer

    def bare(names):
        return {_bare_callee_name(x) for x in names if x}

    root_dir = corpus_dir()
    report = {}
    for lang in langs:
        _, grammar = LANGS[lang]
        parser = ts.get_parser(grammar)
        stats = collections.Counter()
        only_a, only_n, ex = collections.Counter(), collections.Counter(), {"a": {}, "n": {}, "err": []}
        t0 = time.time()
        for p in sample_files(lang, n, AGREE_SEED):
            try:
                src = p.read_text(encoding="utf-8", errors="replace")
                content = src.encode("utf-8")
                an = get_analyzer(str(p))(str(p))
                analyzer_names, ranges = set(), []
                for fn in an.get_structure().get("functions", []):
                    analyzer_names |= bare(fn.get("calls") or [])
                    ranges.append((fn.get("line", 0), fn.get("line_end", fn.get("line", 0))))
                tree = tree_root(ts_parse(parser, src))

                def text(node):
                    return content[_zero_arg(node, "start_byte"):_zero_arg(node, "end_byte")].decode("utf-8", "replace")

                nav_names = set()
                hook = getattr(an, "_implicit_call_nodes", None)
                for fnode in _function_scopes(tree, FUNCTION_TYPES, _zero_arg, node_children):
                    try:
                        hits = range_calls(fnode, 1, 10**7, text, implicit_nodes=hook(fnode) if hook else ())
                    except TypeError:  # older tree: range_calls has no implicit_nodes
                        hits = range_calls(fnode, 1, 10**7, text)
                    nav_names |= bare(c["callee"] for c in hits
                                      if any(lo <= c["line"] <= hi for lo, hi in ranges))
            except Exception as e:  # noqa: BLE001 - a sweep must survive one bad file
                stats["errors"] += 1
                ex["err"].append(f"{p.name}: {type(e).__name__}: {str(e)[:80]}")
                continue
            rel = str(p.relative_to(root_dir))
            stats["files"] += 1
            stats["analyzer"] += len(analyzer_names)
            stats["nav"] += len(nav_names)
            stats["agree"] += len(analyzer_names & nav_names)
            for x in analyzer_names - nav_names:
                only_a[x] += 1
                ex["a"].setdefault(x, rel)
            for x in nav_names - analyzer_names:
                only_n[x] += 1
                ex["n"].setdefault(x, rel)
        union = stats["analyzer"] + stats["nav"] - stats["agree"]
        report[lang] = {
            "files": stats["files"], "errors": stats["errors"], "secs": round(time.time() - t0, 1),
            "jaccard": round(stats["agree"] / union, 4) if union else None,
            "only_analyzer": sum(only_a.values()), "only_nav": sum(only_n.values()),
            "top_only_analyzer": [(k, v, ex["a"][k]) for k, v in only_a.most_common(topn)],
            "top_only_nav": [(k, v, ex["n"][k]) for k, v in only_n.most_common(topn)],
            "error_examples": ex["err"][:3],
        }
    return report


def worker_complexity(langs: list[str], n: int) -> dict:
    from reveal.registry import get_analyzer

    root_dir = corpus_dir()
    out: dict = {}
    for lang in langs:
        files = {}
        for p in sample_files(lang, n, COMPLEXITY_SEED):
            try:
                fns = get_analyzer(str(p))(str(p)).get_structure().get("functions", [])
            except Exception:  # noqa: BLE001
                continue
            files[str(p.relative_to(root_dir))] = {
                f"{f['name']}@{f.get('line')}": f.get("complexity") for f in fns}
        out[lang] = files
    return out


# --------------------------------------------------------------------------
# Driver side: picks the tree, launches workers in a subprocess per tree.
# --------------------------------------------------------------------------

def run_worker(src: Path, sweep: str, langs: list[str], n: int, topn: int) -> dict:
    """Run one sweep against the reveal tree at `src` in a fresh interpreter."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        out = tmp.name
    env = dict(os.environ, REVEAL_DISK_CACHE="0", PYTHONPATH=str(src))
    env.pop("PYTHONPYCACHEPREFIX", None)  # never serve another tree's stale bytecode
    cmd = [sys.executable, str(Path(__file__).resolve()), "_worker", sweep,
           "--out", out, "-n", str(n), "--topn", str(topn), "--src", str(src), *langs]
    try:
        subprocess.run(cmd, env=env, check=True)
        return json.loads(Path(out).read_text())
    finally:
        Path(out).unlink(missing_ok=True)


def export_ref(ref: str, dest: Path) -> Path:
    archive = subprocess.run(["git", "-C", str(REPO), "archive", ref],
                             check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)
    return dest


def diff_complexity(base: dict, head: dict) -> dict:
    report = {}
    for lang, head_files in head.items():
        base_files = base.get(lang, {})
        changed_files, changed_funcs, total, examples = 0, 0, 0, []
        for path, funcs in head_files.items():
            before = base_files.get(path)
            if before is None:
                continue
            diffs = {k: (before[k], v) for k, v in funcs.items() if k in before and before[k] != v}
            total += len(funcs)
            if diffs:
                changed_files += 1
                changed_funcs += len(diffs)
                if len(examples) < 5:
                    k, (b, h) = next(iter(diffs.items()))
                    examples.append(f"{path} {k}: {b} -> {h}")
        report[lang] = {"files": len(head_files), "functions": total,
                        "files_changed": changed_files, "functions_changed": changed_funcs,
                        "examples": examples}
    return report


def print_agree(head: dict, base: dict | None) -> None:
    print(f"{'lang':<11}{'files':>6}{'err':>5}{'jaccard':>10}{'only-an':>9}{'only-nav':>9}" + ("   base" if base else ""))
    for lang, r in head.items():
        j = "-" if r["jaccard"] is None else f"{r['jaccard']:.4f}"
        line = f"{lang:<11}{r['files']:>6}{r['errors']:>5}{j:>10}{r['only_analyzer']:>9}{r['only_nav']:>9}"
        if base and lang in base and base[lang]["jaccard"] is not None:
            line += f"   {base[lang]['jaccard']:.4f}"
        print(line)


def print_complexity(rep: dict) -> None:
    print(f"{'lang':<11}{'files':>6}{'funcs':>8}{'files chg':>10}{'funcs chg':>10}")
    for lang, r in rep.items():
        print(f"{lang:<11}{r['files']:>6}{r['functions']:>8}{r['files_changed']:>10}{r['functions_changed']:>10}")
        for e in r["examples"][:2]:
            print(f"    {e}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sweep", choices=["agree", "complexity", "_worker"])
    ap.add_argument("langs", nargs="*", help="languages to sweep (default: all present in the corpus)")
    ap.add_argument("-n", type=int, default=60, help="files sampled per language (default 60)")
    ap.add_argument("--base-ref", help="git ref to compare against (required for complexity)")
    ap.add_argument("-o", "--out", help="write the full JSON report here")
    ap.add_argument("--min-jaccard", type=float,
                    help="agree: exit 1 if any language's analyzer/nav agreement is below this (pre-release gate)")
    ap.add_argument("--floor", action="append", default=[], metavar="LANG=VALUE",
                    help="agree: per-language override of --min-jaccard for known, tracked gaps (repeatable)")
    ap.add_argument("--topn", type=int, default=8, help="agree: top one-sided names kept per language")
    ap.add_argument("--src", help=argparse.SUPPRESS)
    args = ap.parse_intermixed_args(argv)

    if args.sweep == "_worker":  # re-invoked by run_worker with PYTHONPATH set
        import reveal
        if not Path(reveal.__file__).resolve().is_relative_to(Path(args.src).resolve()):
            sys.exit(f"worker imported reveal from {reveal.__file__}, not {args.src}")
        sweep, langs = args.langs[0], args.langs[1:]
        result = worker_agree(langs, args.n, args.topn) if sweep == "agree" else worker_complexity(langs, args.n)
        Path(args.out).write_text(json.dumps(result))
        return 0

    langs = args.langs
    unknown = [lang for lang in langs if lang not in LANGS]
    if unknown:
        ap.error(f"unknown language(s): {', '.join(unknown)} (known: {', '.join(LANGS)})")
    present = [lang for lang in (langs or LANGS) if (corpus_dir() / lang).is_dir()]
    if not present:
        print(f"corpus not found at {corpus_dir()} -- run scripts/fetch_corpus.py; nothing to sweep")
        return 0
    if args.sweep == "complexity" and not args.base_ref:
        ap.error("complexity needs --base-ref (it diffs base vs current tree)")

    head = run_worker(REPO, args.sweep, present, args.n, args.topn)
    base = None
    if args.base_ref:
        with tempfile.TemporaryDirectory(prefix="reveal-base-") as td:
            base_src = export_ref(args.base_ref, Path(td))
            base = run_worker(base_src, args.sweep, present, args.n, args.topn)

    if args.sweep == "agree":
        print_agree(head, base)
        full = {"head": head, "base": base}
    else:
        rep = diff_complexity(base, head)
        print_complexity(rep)
        full = rep
    if args.out:
        Path(args.out).write_text(json.dumps(full, indent=1))
        print(f"wrote {args.out}")
    if args.min_jaccard is not None and args.sweep == "agree":
        floors = {k: float(v) for k, _, v in (f.partition("=") for f in args.floor)}
        low = {lang: r["jaccard"] for lang, r in head.items()
               if r["jaccard"] is not None and r["jaccard"] < floors.get(lang, args.min_jaccard)}
        if low:
            print(f"\n❌ agreement below floor: " + ", ".join(f"{k}={v}" for k, v in low.items()))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
