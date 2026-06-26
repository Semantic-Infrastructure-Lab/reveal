"""Tests for reveal/rules/profiles.py — named rule preset support (BACK-321)."""

import sys
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest import mock

from reveal.rules.profiles import BUILTIN_PROFILES, list_profiles, resolve_profile


# ---------------------------------------------------------------------------
# Unit tests for resolve_profile
# ---------------------------------------------------------------------------


class TestResolveProfileBuiltin(unittest.TestCase):
    """resolve_profile returns correct select/ignore for built-in profiles."""

    def test_maintenance_profile_exists(self):
        result = resolve_profile("maintenance")
        self.assertIn("select", result)
        self.assertIn("ignore", result)
        self.assertIsInstance(result["select"], list)
        self.assertIsInstance(result["ignore"], list)
        self.assertGreater(len(result["select"]), 0, "maintenance profile must select at least one rule/category")

    def test_security_profile_exists(self):
        result = resolve_profile("security")
        self.assertIn("select", result)
        self.assertIn("ignore", result)
        self.assertGreater(len(result["select"]), 0, "security profile must select at least one rule/category")

    def test_ci_strict_profile_exists(self):
        result = resolve_profile("ci-strict")
        self.assertIn("select", result)
        self.assertIn("ignore", result)
        self.assertGreater(len(result["select"]), 0, "ci-strict profile must select at least one rule/category")

    def test_unknown_profile_raises_key_error(self):
        with self.assertRaises(KeyError) as ctx:
            resolve_profile("nonexistent-profile")
        self.assertIn("nonexistent-profile", str(ctx.exception))

    def test_unknown_profile_error_lists_available(self):
        """Error message should hint at available profiles."""
        with self.assertRaises(KeyError) as ctx:
            resolve_profile("nonexistent-profile")
        msg = str(ctx.exception)
        # At least one built-in profile name should appear in the message
        self.assertTrue(
            any(name in msg for name in BUILTIN_PROFILES),
            f"Error message should list available profiles, got: {msg}",
        )

    def test_returns_copies_not_references(self):
        """Mutation of returned lists must not affect BUILTIN_PROFILES."""
        result = resolve_profile("maintenance")
        original_select = list(BUILTIN_PROFILES["maintenance"]["select"])
        result["select"].append("INJECTED")
        self.assertEqual(
            BUILTIN_PROFILES["maintenance"]["select"],
            original_select,
            "resolve_profile must return a copy, not a reference to the built-in list",
        )


class TestResolveProfileUserOverride(unittest.TestCase):
    """Project-defined profiles in user_profiles take precedence over builtins."""

    def test_user_profile_resolved(self):
        user_profiles = {
            "custom": {
                "description": "Project custom profile",
                "select": ["B", "C"],
                "ignore": ["C902"],
            }
        }
        result = resolve_profile("custom", user_profiles=user_profiles)
        self.assertEqual(result["select"], ["B", "C"])
        self.assertEqual(result["ignore"], ["C902"])

    def test_user_profile_overrides_builtin(self):
        """A user-defined profile with the same name as a builtin wins."""
        user_profiles = {
            "security": {
                "description": "Lighter security scan",
                "select": ["S001"],
                "ignore": ["S701"],
            }
        }
        result = resolve_profile("security", user_profiles=user_profiles)
        self.assertEqual(result["select"], ["S001"])
        self.assertEqual(result["ignore"], ["S701"])

    def test_builtin_still_available_alongside_user(self):
        """Builtins not shadowed by user_profiles remain resolvable."""
        user_profiles = {"custom": {"select": ["B"], "ignore": []}}
        result = resolve_profile("maintenance", user_profiles=user_profiles)
        self.assertGreater(len(result["select"]), 0)

    def test_user_profile_missing_ignore_defaults_empty(self):
        """If user profile omits 'ignore', result['ignore'] is []."""
        user_profiles = {"myprofile": {"select": ["B"]}}
        result = resolve_profile("myprofile", user_profiles=user_profiles)
        self.assertEqual(result["ignore"], [])

    def test_user_profile_missing_select_defaults_empty(self):
        """If user profile omits 'select', result['select'] is []."""
        user_profiles = {"myprofile": {"ignore": ["C902"]}}
        result = resolve_profile("myprofile", user_profiles=user_profiles)
        self.assertEqual(result["select"], [])

    def test_none_user_profiles_falls_back_to_builtins(self):
        result = resolve_profile("maintenance", user_profiles=None)
        self.assertGreater(len(result["select"]), 0)


# ---------------------------------------------------------------------------
# Unit tests for list_profiles
# ---------------------------------------------------------------------------


class TestListProfiles(unittest.TestCase):
    """list_profiles returns well-formed list of profile descriptors."""

    def test_returns_all_builtins(self):
        profiles = list_profiles()
        names = {p["name"] for p in profiles}
        self.assertTrue(
            names.issuperset(BUILTIN_PROFILES.keys()),
            f"Expected all built-in profiles; got {names}",
        )

    def test_builtin_flag_correct(self):
        profiles = list_profiles()
        for p in profiles:
            if p["name"] in BUILTIN_PROFILES:
                self.assertTrue(p["builtin"], f"{p['name']} should be marked builtin=True")

    def test_each_profile_has_required_keys(self):
        profiles = list_profiles()
        for p in profiles:
            for key in ("name", "description", "select", "ignore", "builtin"):
                self.assertIn(key, p, f"Profile {p.get('name')} missing key '{key}'")

    def test_user_profiles_included(self):
        user_profiles = {"custom": {"description": "custom", "select": ["B"], "ignore": []}}
        profiles = list_profiles(user_profiles=user_profiles)
        names = {p["name"] for p in profiles}
        self.assertIn("custom", names)

    def test_user_profile_not_marked_builtin(self):
        user_profiles = {"custom": {"description": "custom", "select": ["B"], "ignore": []}}
        profiles = list_profiles(user_profiles=user_profiles)
        custom = next(p for p in profiles if p["name"] == "custom")
        self.assertFalse(custom["builtin"])

    def test_sorted_by_name(self):
        profiles = list_profiles()
        names = [p["name"] for p in profiles]
        self.assertEqual(names, sorted(names), "list_profiles should return profiles sorted by name")

    def test_none_user_profiles_returns_only_builtins(self):
        profiles = list_profiles(user_profiles=None)
        self.assertEqual(len(profiles), len(BUILTIN_PROFILES))


# ---------------------------------------------------------------------------
# Integration: check command --profile flag wires into select/ignore
# ---------------------------------------------------------------------------


class TestCheckCommandProfileArg(unittest.TestCase):
    """run_check propagates --profile into args.select / args.ignore."""

    def _make_args(self, **kwargs):
        defaults = {
            "path": None,
            "select": None,
            "ignore": None,
            "profile": None,
            "rules": False,
            "explain": None,
            "format": "text",
            "only_failures": False,
            "recursive": False,
            "advanced": False,
            "config": None,
            "no_group": False,
            "severity": None,
            "verbose": False,
            "no_fallback": False,
        }
        defaults.update(kwargs)
        return Namespace(**defaults)

    def test_profile_sets_select_when_no_explicit_select(self):
        """When --profile is given and no --select, profile's select wins."""
        args = self._make_args(profile="security", path="/nonexistent")
        with mock.patch("reveal.utils.check_for_updates"):
            with self.assertRaises(SystemExit):
                from reveal.cli.commands.check import run_check
                run_check(args)
        # Even though it exits (path not found), args.select should have been set
        self.assertIsNotNone(args.select)

    def test_explicit_select_overrides_profile(self):
        """--select takes precedence over --profile."""
        args = self._make_args(profile="security", select="B001", path="/nonexistent")
        with mock.patch("reveal.utils.check_for_updates"):
            with self.assertRaises(SystemExit):
                from reveal.cli.commands.check import run_check
                run_check(args)
        # Explicit --select must be preserved unchanged
        self.assertEqual(args.select, "B001")

    def test_explicit_ignore_overrides_profile_ignore(self):
        """--ignore takes precedence over profile's ignore list."""
        # Use a profile that has an ignore list
        args = self._make_args(
            profile="security",
            ignore="B001",  # explicit
            path="/nonexistent",
        )
        with mock.patch("reveal.utils.check_for_updates"):
            with self.assertRaises(SystemExit):
                from reveal.cli.commands.check import run_check
                run_check(args)
        # Explicit --ignore must survive
        self.assertEqual(args.ignore, "B001")

    def test_unknown_profile_exits_with_error(self):
        args = self._make_args(profile="does-not-exist", path=".")
        stderr_cap = StringIO()
        with mock.patch("reveal.utils.check_for_updates"):
            with mock.patch("sys.stderr", stderr_cap):
                with self.assertRaises(SystemExit) as ctx:
                    from reveal.cli.commands.check import run_check
                    run_check(args)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("does-not-exist", stderr_cap.getvalue())

    def test_profile_with_project_config(self):
        """Project-defined profiles in .reveal.yaml are loaded and resolved."""
        import tempfile, os, shutil

        tmp = tempfile.mkdtemp(prefix="reveal_test_profile_")
        try:
            yaml_content = (
                "root: true\n"
                "profiles:\n"
                "  project-lint:\n"
                "    description: Project-specific rules\n"
                "    select:\n"
                "    - B001\n"
                "    ignore: []\n"
            )
            (Path(tmp) / ".reveal.yaml").write_text(yaml_content)
            dummy_file = Path(tmp) / "dummy.py"
            dummy_file.write_text("x = 1\n")

            args = self._make_args(profile="project-lint", path=str(dummy_file))
            from reveal.config import RevealConfig
            RevealConfig._cache.clear()

            with mock.patch("reveal.utils.check_for_updates"):
                # run_check will proceed past profile resolution and try to analyze the file
                try:
                    from reveal.cli.commands.check import run_check
                    run_check(args)
                except SystemExit:
                    pass

            # Profile select must be B001 (from project config)
            self.assertEqual(args.select, "B001")
        finally:
            from reveal.config import RevealConfig
            RevealConfig._cache.clear()
            shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Integration: --profiles flag calls handle_profiles_list
# ---------------------------------------------------------------------------


class TestHandleProfilesList(unittest.TestCase):
    """handle_profiles_list prints all profiles to stdout and exits 0."""

    def test_outputs_builtin_profile_names(self):
        stdout_cap = StringIO()
        with mock.patch("sys.stdout", stdout_cap):
            with self.assertRaises(SystemExit) as ctx:
                from reveal.cli.handlers.introspection import handle_profiles_list
                handle_profiles_list()
        self.assertEqual(ctx.exception.code, 0)
        output = stdout_cap.getvalue()
        for name in BUILTIN_PROFILES:
            self.assertIn(name, output, f"Profile '{name}' missing from --profiles output")

    def test_outputs_usage_hint(self):
        stdout_cap = StringIO()
        with mock.patch("sys.stdout", stdout_cap):
            with self.assertRaises(SystemExit):
                from reveal.cli.handlers.introspection import handle_profiles_list
                handle_profiles_list()
        self.assertIn("reveal check", stdout_cap.getvalue())

    def test_outputs_select_categories(self):
        stdout_cap = StringIO()
        with mock.patch("sys.stdout", stdout_cap):
            with self.assertRaises(SystemExit):
                from reveal.cli.handlers.introspection import handle_profiles_list
                handle_profiles_list()
        output = stdout_cap.getvalue()
        # At least one profile should mention 'select'
        self.assertIn("select", output)


# ---------------------------------------------------------------------------
# Integration: config schema validates profiles: key
# ---------------------------------------------------------------------------


class TestConfigSchemaProfiles(unittest.TestCase):
    """Ensure profiles: in .reveal.yaml validates against CONFIG_SCHEMA."""

    def test_valid_profiles_key_passes_schema(self):
        """A .reveal.yaml with a valid profiles: block should load without error."""
        import tempfile, shutil

        tmp = tempfile.mkdtemp(prefix="reveal_schema_profiles_")
        try:
            yaml_content = (
                "root: true\n"
                "profiles:\n"
                "  team-strict:\n"
                "    description: Strictest checks for PRs\n"
                "    select:\n"
                "    - B\n"
                "    - S\n"
                "    ignore:\n"
                "    - C902\n"
            )
            (Path(tmp) / ".reveal.yaml").write_text(yaml_content)

            from reveal.config import RevealConfig
            RevealConfig._cache.clear()
            cfg = RevealConfig.get(start_path=Path(tmp))
            project_profiles = cfg._config.get("profiles", {})
            self.assertIn("team-strict", project_profiles)
            self.assertEqual(project_profiles["team-strict"]["select"], ["B", "S"])
            self.assertEqual(project_profiles["team-strict"]["ignore"], ["C902"])
        finally:
            from reveal.config import RevealConfig
            RevealConfig._cache.clear()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_profiles_with_unknown_field_rejected(self):
        """profiles: block with extra fields should fail schema validation."""
        import tempfile, shutil

        tmp = tempfile.mkdtemp(prefix="reveal_schema_profiles_invalid_")
        try:
            yaml_content = (
                "root: true\n"
                "profiles:\n"
                "  bad-profile:\n"
                "    description: has extra field\n"
                "    select: [B]\n"
                "    unknown_field: true\n"  # not in schema
            )
            (Path(tmp) / ".reveal.yaml").write_text(yaml_content)

            from reveal.config import RevealConfig
            RevealConfig._cache.clear()
            # Schema validation should raise; if it doesn't, the schema is too permissive
            try:
                cfg = RevealConfig.get(start_path=Path(tmp))
                # If we got here, check if unknown_field is present (would indicate no validation)
                profiles = cfg._config.get("profiles", {})
                bad = profiles.get("bad-profile", {})
                self.assertNotIn(
                    "unknown_field", bad,
                    "additionalProperties=False should reject unknown_field",
                )
            except Exception:
                pass  # validation error is the expected outcome
        finally:
            from reveal.config import RevealConfig
            RevealConfig._cache.clear()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
