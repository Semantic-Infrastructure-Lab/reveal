"""Tests for reveal/utils/provenance.py — execution provenance (BACK-881)."""

from pathlib import Path

import pytest

from reveal.utils.provenance import build_execution_provenance, _git_state, _config_digest

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


class TestBuildExecutionProvenance:
    """Test build_execution_provenance() field presence and shape."""

    def test_always_present_fields(self):
        prov = build_execution_provenance()

        assert isinstance(prov['reveal_version'], str)
        assert isinstance(prov['command'], str)
        assert isinstance(prov['platform'], str)
        assert isinstance(prov['python_version'], str)
        # repo/config_digest are Optional — presence, not truthiness, is guaranteed
        assert 'repo' in prov
        assert 'config_digest' in prov

    def test_repo_state_inside_git_repo(self):
        # This repo itself is a git checkout
        prov = build_execution_provenance(cwd=Path(__file__).resolve().parent)

        assert prov['repo'] is not None
        assert 'commit' in prov['repo']
        assert 'dirty' in prov['repo']
        assert isinstance(prov['repo']['commit'], str)
        assert len(prov['repo']['commit']) > 0

    def test_repo_state_outside_git_repo(self, tmp_path):
        assert _git_state(tmp_path) is None

    def test_config_digest_is_stable_for_same_cwd(self, tmp_path):
        # No .reveal.yaml in an empty tmp dir — still returns *some* digest
        # (the resolved default config), and it must be deterministic.
        digest1 = _config_digest(tmp_path)
        digest2 = _config_digest(tmp_path)

        assert digest1 == digest2

    def test_json_serializable(self):
        import json
        from reveal.utils import safe_json_dumps

        prov = build_execution_provenance()

        # Must round-trip cleanly through the same encoder print_json_result uses
        decoded = json.loads(safe_json_dumps(prov))
        assert decoded['reveal_version'] == prov['reveal_version']
