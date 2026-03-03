"""Subcommand implementations for reveal CLI.

Each module in this package implements one subcommand:
  check.py  — `reveal check <path>` (quality rules)

Pattern for each module:
  add_<name>_subcommand(subparsers, global_opts) — registers with argparse
  add_arguments(parser)                           — defines subcommand flags
  run_<name>(args)                                — canonical implementation
"""
