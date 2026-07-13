"""BACK-522: unrecognized-argument errors must not dump every adapter's flags.

Before the fix, `create_argument_parser()` built one flat ArgumentParser with
every adapter-specific flag group (nginx/cpanel/ssl/markdown/...) registered
unconditionally, so argparse's default "unrecognized arguments" error printed
a usage block listing all of them — misleading for e.g. a plain `.py` file
error (repro: `reveal bots/nq_bot/bot.py 1 120`). The fix scopes that one
error case to a short positional-only usage line plus a pointer to --help /
help://quick; other argparse errors are unaffected.
"""

import io
import contextlib

import pytest

from reveal.cli.parser import create_argument_parser


def _capture_error_exit(parser, argv):
    """Run parse_args expecting SystemExit(2); return captured stderr."""
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(argv)
    assert exc_info.value.code == 2
    return stderr.getvalue()


class TestBack522ScopedUsageError:
    def test_unrecognized_argument_usage_is_scoped(self):
        """Extra positional arg gets a short usage, not the full flag dump."""
        parser = create_argument_parser('test')
        stderr = _capture_error_exit(parser, ['example.py', '1', '120'])

        assert 'unrecognized arguments: 120' in stderr
        # None of the adapter-specific flags from unrelated subsystems appear.
        for unrelated_flag in (
            '--validate-nginx-acme', '--cpanel-certs', '--global-audit',
            '--check-acl', '--dns-verified', '--probe-http',
        ):
            assert unrelated_flag not in stderr

    def test_unrecognized_argument_usage_points_to_help(self):
        """Scoped error still tells the user/agent how to get the full reference."""
        parser = create_argument_parser('test')
        stderr = _capture_error_exit(parser, ['example.py', 'x', 'y'])

        assert '--help' in stderr
        assert 'help://quick' in stderr

    def test_other_errors_keep_default_usage(self):
        """A non-unrecognized-arguments error (bad choice) is untouched."""
        parser = create_argument_parser('test')
        stderr = _capture_error_exit(
            parser, ['example.py', '--format', 'not-a-real-format']
        )

        assert 'unrecognized arguments' not in stderr
        assert 'invalid choice' in stderr
        # The default path still prints the full usage block for this case.
        assert '--format' in stderr

    def test_fail_before_regression(self):
        """Sanity pin: without the fix, the unrelated flag WOULD have appeared.

        Directly asserts the old (unscoped) argparse.ArgumentParser.error
        path is what BACK-522 replaced, by checking format_usage() on the
        raw parser contains the unrelated flag the scoped path suppresses.
        """
        parser = create_argument_parser('test')
        full_usage = parser.format_usage()
        assert '--cpanel-certs' in full_usage
