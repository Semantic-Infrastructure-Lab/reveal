"""reveal offline — pre-download tree-sitter grammars for offline/air-gapped use (BACK-980).

Follow-up to BACK-979: tree-sitter grammars are fetched from the network on
first use of each language. This command lets a user pay that cost once,
deliberately, instead of hitting it silently mid-task on an air-gapped host.
"""

import argparse
import sys
from argparse import Namespace


def create_offline_parser() -> argparse.ArgumentParser:
    """Create and return the argument parser for 'reveal offline'."""
    parser = argparse.ArgumentParser(
        prog='reveal offline',
        description='Pre-download tree-sitter grammars so reveal works without network access.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal offline                              # download every grammar\n"
            "  reveal offline --languages python,go,rust   # download just these\n"
            "  reveal offline --disable-update-check       # also stop the daily PyPI check\n"
            "\n"
            "See INSTALL.md#network-requirements for background on why this is needed.\n"
        ),
    )
    parser.add_argument(
        '--languages',
        metavar='LANG,LANG,...',
        help="Comma-separated language names to download (default: all — see 'reveal --languages')",
    )
    parser.add_argument(
        '--disable-update-check',
        action='store_true',
        help='Persist REVEAL_NO_UPDATE_CHECK into ~/.config/reveal/config.yaml',
    )
    return parser


def run_offline(args: Namespace) -> None:
    """Run 'reveal offline': download grammars, optionally persist update-check opt-out."""
    if args.disable_update_check:
        from reveal.config import disable_update_check_permanently
        disable_update_check_permanently()

    import tree_sitter_language_pack as tslp

    if args.languages:
        names = [n.strip() for n in args.languages.split(',') if n.strip()]
        if not names:
            print("Error: --languages given but no language names parsed", file=sys.stderr)
            sys.exit(1)
        print(f"Downloading {len(names)} grammar(s): {', '.join(names)}")
        try:
            count = tslp.download(names)
        except Exception as e:
            print(f"❌ Download failed: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("Downloading all tree-sitter grammars (this may take a while)...")
        try:
            count = tslp.download_all()
        except Exception as e:
            print(f"❌ Download failed: {e}", file=sys.stderr)
            sys.exit(1)

    print(f"✅ Downloaded {count} grammar(s) to the local cache")
