"""Tests for BACK-444's language capability registry (reveal/capabilities.py).

The most important test here is TestEveryRegisteredAnalyzerHasAProfile — a
guard against future drift: any new analyzer added to reveal/analyzers/*.py
and wired into reveal/registry.py's _ANALYZER_REGISTRY must get a
LanguageCapability profile in the same change, or this test fails.
"""

import unittest

from reveal.registry import get_analyzer_mapping
from reveal.capabilities import (
    CAPABILITIES,
    LanguageCapability,
    get_capability,
    get_capability_for_extension,
    get_all_capabilities,
    VARFLOW_VERIFIED,
    VARFLOW_SMOKE_TESTED,
    VARFLOW_NOT_APPLICABLE,
    VARFLOW_UNTESTED,
    CONFORMANCE_TIER1_VERIFIED,
    CONFORMANCE_SMOKE_TESTED,
    CONFORMANCE_STRUCTURE_ONLY,
    CONFORMANCE_UNTESTED,
)


class TestEveryRegisteredAnalyzerHasAProfile(unittest.TestCase):
    """The guard test: every analyzer class actually wired into the
    registry must have a capability profile. This is what stops the
    capability registry from silently drifting out of date as new
    languages land (the exact problem BACK-444 was filed to prevent).
    """

    def test_every_registered_analyzer_class_has_a_capability_profile(self):
        registered_classes = {cls.__name__ for cls in get_analyzer_mapping().values()}
        missing = registered_classes - set(CAPABILITIES.keys())
        self.assertEqual(
            missing, set(),
            f"Analyzer(s) registered in reveal/registry.py with no "
            f"LanguageCapability profile in reveal/capabilities.py: {sorted(missing)}. "
            f"Add a profile grounded in real test/doc evidence — see BACK-444."
        )

    def test_guard_actually_fails_for_an_unprofiled_class(self):
        """Sanity-check the assertion logic itself: simulate a newly
        registered analyzer with no profile and confirm the same check
        this test file relies on would catch it.
        """
        registered_classes = {cls.__name__ for cls in get_analyzer_mapping().values()}
        fake_new_analyzer = "TotallyNewLanguageAnalyzer"
        self.assertNotIn(fake_new_analyzer, CAPABILITIES)
        simulated_registered = registered_classes | {fake_new_analyzer}
        missing = simulated_registered - set(CAPABILITIES.keys())
        self.assertEqual(missing, {fake_new_analyzer})

    def test_every_profile_key_matches_a_real_class_name_pattern(self):
        # Every key should look like a class name (defensive against typos
        # that would silently create a profile nothing ever looks up).
        for key in CAPABILITIES:
            self.assertTrue(key.endswith("Analyzer"), key)


class TestLanguageCapabilityFieldValidation(unittest.TestCase):

    def test_all_varflow_values_are_known_levels(self):
        valid = {VARFLOW_VERIFIED, VARFLOW_SMOKE_TESTED, VARFLOW_NOT_APPLICABLE, VARFLOW_UNTESTED}
        for name, cap in CAPABILITIES.items():
            self.assertIn(cap.varflow, valid, f"{name}: invalid varflow level {cap.varflow!r}")

    def test_all_conformance_levels_are_known(self):
        valid = {
            CONFORMANCE_TIER1_VERIFIED, CONFORMANCE_SMOKE_TESTED,
            CONFORMANCE_STRUCTURE_ONLY, CONFORMANCE_UNTESTED,
        }
        for name, cap in CAPABILITIES.items():
            self.assertIn(cap.conformance_level, valid, f"{name}: invalid conformance_level {cap.conformance_level!r}")

    def test_imports_unused_is_bool_or_none(self):
        for name, cap in CAPABILITIES.items():
            self.assertIn(cap.imports_unused, (True, False, None), name)

    def test_known_limitations_is_a_list_of_strings(self):
        for name, cap in CAPABILITIES.items():
            self.assertIsInstance(cap.known_limitations, list, name)
            for item in cap.known_limitations:
                self.assertIsInstance(item, str, name)

    def test_tier1_languages_are_varflow_verified(self):
        tier1_languages = {
            "python", "rust", "go", "c", "cpp", "java", "csharp",
            "javascript", "typescript",
        }
        found = {
            cap.language for cap in CAPABILITIES.values()
            if cap.conformance_level == CONFORMANCE_TIER1_VERIFIED
        }
        self.assertEqual(found, tier1_languages)
        for cap in CAPABILITIES.values():
            if cap.conformance_level == CONFORMANCE_TIER1_VERIFIED:
                self.assertEqual(cap.varflow, VARFLOW_VERIFIED, cap.language)

    def test_structure_only_languages_have_not_applicable_varflow(self):
        for cap in CAPABILITIES.values():
            if cap.conformance_level == CONFORMANCE_STRUCTURE_ONLY:
                self.assertEqual(cap.varflow, VARFLOW_NOT_APPLICABLE, cap.language)

    def test_rejects_unknown_varflow_level(self):
        with self.assertRaises(ValueError):
            LanguageCapability(
                language="madeup", analyzer="x.Y", function_body_shape="n/a",
                varflow="totally-invalid-level", imports_unused=None,
                import_resolution="n/a", conformance_level=CONFORMANCE_UNTESTED,
            )

    def test_rejects_unknown_conformance_level(self):
        with self.assertRaises(ValueError):
            LanguageCapability(
                language="madeup", analyzer="x.Y", function_body_shape="n/a",
                varflow=VARFLOW_UNTESTED, imports_unused=None,
                import_resolution="n/a", conformance_level="not-a-real-tier",
            )


class TestLookupHelpers(unittest.TestCase):

    def test_get_capability_by_class(self):
        from reveal.analyzers.python import PythonAnalyzer
        cap = get_capability(PythonAnalyzer)
        self.assertIsNotNone(cap)
        self.assertEqual(cap.language, "python")

    def test_get_capability_by_instance_class(self):
        from reveal.analyzers.rust import RustAnalyzer
        cap = get_capability(RustAnalyzer)
        self.assertEqual(cap.language, "rust")

    def test_get_capability_for_extension(self):
        cap = get_capability_for_extension(".py")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.language, "python")

    def test_get_capability_for_extension_case_insensitive(self):
        cap = get_capability_for_extension(".PY")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.language, "python")

    def test_get_capability_for_unknown_extension(self):
        self.assertIsNone(get_capability_for_extension(".totally-not-a-real-ext"))

    def test_get_all_capabilities_returns_a_copy(self):
        caps = get_all_capabilities()
        caps["bogus"] = None
        self.assertNotIn("bogus", CAPABILITIES)


if __name__ == "__main__":
    unittest.main()
