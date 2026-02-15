"""Tests for reveal.cli.scaffold modules."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


# ============================================================================
# Test adapter.py
# ============================================================================

class TestAdapterScaffold:
    """Tests for adapter scaffolding."""

    def test_scaffold_adapter_basic(self):
        """Test basic adapter scaffolding."""
        from reveal.cli.scaffold.adapter import scaffold_adapter

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create required directory structure
            (output_dir / 'reveal' / 'adapters').mkdir(parents=True)
            (output_dir / 'tests').mkdir(parents=True)
            (output_dir / 'reveal' / 'docs').mkdir(parents=True)

            result = scaffold_adapter('github', 'github://', output_dir=output_dir)

            assert 'adapter_file' in result
            assert 'test_file' in result
            assert 'doc_file' in result
            assert 'next_steps' in result
            assert 'error' not in result

            # Verify files were created
            adapter_file = Path(result['adapter_file'])
            assert adapter_file.exists()
            assert adapter_file.name == 'github.py'

            test_file = Path(result['test_file'])
            assert test_file.exists()
            assert test_file.name == 'test_github_adapter.py'

            doc_file = Path(result['doc_file'])
            assert doc_file.exists()

    def test_scaffold_adapter_name_normalization(self):
        """Test adapter name normalization (hyphens to underscores)."""
        from reveal.cli.scaffold.adapter import scaffold_adapter

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / 'reveal' / 'adapters').mkdir(parents=True)
            (output_dir / 'tests').mkdir(parents=True)
            (output_dir / 'reveal' / 'docs').mkdir(parents=True)

            result = scaffold_adapter('my-adapter', 'custom://', output_dir=output_dir)

            adapter_file = Path(result['adapter_file'])
            assert adapter_file.name == 'my_adapter.py'

    def test_scaffold_adapter_class_name_generation(self):
        """Test class name generation (PascalCase)."""
        from reveal.cli.scaffold.adapter import scaffold_adapter

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / 'reveal' / 'adapters').mkdir(parents=True)
            (output_dir / 'tests').mkdir(parents=True)
            (output_dir / 'reveal' / 'docs').mkdir(parents=True)

            result = scaffold_adapter('my_custom_adapter', 'custom://', output_dir=output_dir)

            # Read adapter file and check for class name
            adapter_file = Path(result['adapter_file'])
            content = adapter_file.read_text()
            assert 'MyCustomAdapter' in content

    def test_scaffold_adapter_uri_scheme_normalization(self):
        """Test URI scheme normalization (strip ://)."""
        from reveal.cli.scaffold.adapter import scaffold_adapter

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / 'reveal' / 'adapters').mkdir(parents=True)
            (output_dir / 'tests').mkdir(parents=True)
            (output_dir / 'reveal' / 'docs').mkdir(parents=True)

            result = scaffold_adapter('test', 'custom://', output_dir=output_dir)

            # Read adapter file and check scheme is normalized
            adapter_file = Path(result['adapter_file'])
            content = adapter_file.read_text()
            assert 'custom' in content.lower()

    def test_scaffold_adapter_existing_files_no_force(self):
        """Test scaffolding fails when files exist without force flag."""
        from reveal.cli.scaffold.adapter import scaffold_adapter

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / 'reveal' / 'adapters').mkdir(parents=True)
            (output_dir / 'tests').mkdir(parents=True)
            (output_dir / 'reveal' / 'docs').mkdir(parents=True)

            # Create first time
            scaffold_adapter('test', 'test://', output_dir=output_dir)

            # Try to create again without force
            result = scaffold_adapter('test', 'test://', output_dir=output_dir, force=False)

            assert 'error' in result
            assert result['error'] == 'Files exist'
            assert 'existing_files' in result
            assert len(result['existing_files']) > 0

    def test_scaffold_adapter_existing_files_with_force(self):
        """Test scaffolding overwrites files when force=True."""
        from reveal.cli.scaffold.adapter import scaffold_adapter

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            (output_dir / 'reveal' / 'adapters').mkdir(parents=True)
            (output_dir / 'tests').mkdir(parents=True)
            (output_dir / 'reveal' / 'docs').mkdir(parents=True)

            # Create first time
            result1 = scaffold_adapter('test', 'test://', output_dir=output_dir)
            adapter_file = Path(result1['adapter_file'])

            # Modify file
            adapter_file.write_text("# Modified content")

            # Create again with force
            result2 = scaffold_adapter('test', 'test://', output_dir=output_dir, force=True)

            assert 'error' not in result2
            # File should be overwritten
            content = adapter_file.read_text()
            assert "# Modified content" not in content

    def test_scaffold_adapter_no_output_dir_not_in_project(self):
        """Test scaffolding fails when not in reveal project and no output_dir."""
        from reveal.cli.scaffold.adapter import scaffold_adapter

        # Mock _find_reveal_root to return None
        with patch('reveal.cli.scaffold.adapter._find_reveal_root', return_value=None):
            result = scaffold_adapter('test', 'test://')

            assert 'error' in result
            assert result['error'] == 'Not in reveal project'

    def test_scaffold_adapter_creates_directories(self):
        """Test scaffolding creates parent directories if they don't exist."""
        from reveal.cli.scaffold.adapter import scaffold_adapter

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            # Don't create directories - let scaffold_adapter do it

            result = scaffold_adapter('test', 'test://', output_dir=output_dir)

            assert 'error' not in result
            assert Path(result['adapter_file']).exists()
            assert Path(result['test_file']).exists()
            assert Path(result['doc_file']).exists()

    def test_find_reveal_root_found(self):
        """Test _find_reveal_root finds reveal project root."""
        from reveal.cli.scaffold.adapter import _find_reveal_root

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'reveal' / 'adapters').mkdir(parents=True)

            # Create a subdirectory and change to it
            subdir = root / 'some' / 'nested' / 'dir'
            subdir.mkdir(parents=True)

            with patch('pathlib.Path.cwd', return_value=subdir):
                found_root = _find_reveal_root()
                assert found_root == root

    def test_find_reveal_root_not_found(self):
        """Test _find_reveal_root returns None when not in project."""
        from reveal.cli.scaffold.adapter import _find_reveal_root

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('pathlib.Path.cwd', return_value=Path(tmpdir)):
                found_root = _find_reveal_root()
                assert found_root is None


# ============================================================================
# Test analyzer.py
# ============================================================================

class TestAnalyzerScaffold:
    """Tests for analyzer scaffolding."""

    def test_scaffold_analyzer_basic(self):
        """Test basic analyzer scaffolding."""
        from reveal.cli.scaffold.analyzer import scaffold_analyzer

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = scaffold_analyzer('xyz', '.xyz', output_dir=output_dir)

            assert 'analyzer_file' in result
            assert 'test_file' in result
            assert 'doc_file' in result
            assert 'next_steps' in result
            assert 'error' not in result

            # Verify files were created
            analyzer_file = Path(result['analyzer_file'])
            assert analyzer_file.exists()
            assert analyzer_file.name == 'xyz.py'

    def test_scaffold_analyzer_extension_normalization(self):
        """Test extension normalization (adds dot if missing)."""
        from reveal.cli.scaffold.analyzer import scaffold_analyzer

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = scaffold_analyzer('xyz', 'xyz', output_dir=output_dir)

            # Read analyzer file and check extension has dot
            analyzer_file = Path(result['analyzer_file'])
            content = analyzer_file.read_text()
            assert '.xyz' in content

    def test_scaffold_analyzer_name_normalization(self):
        """Test analyzer name normalization."""
        from reveal.cli.scaffold.analyzer import scaffold_analyzer

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = scaffold_analyzer('My-Custom Lang', '.mcl', output_dir=output_dir)

            analyzer_file = Path(result['analyzer_file'])
            assert analyzer_file.name == 'my_custom_lang.py'

    def test_scaffold_analyzer_class_name_generation(self):
        """Test class name generation (PascalCase)."""
        from reveal.cli.scaffold.analyzer import scaffold_analyzer

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = scaffold_analyzer('my_custom_lang', '.mcl', output_dir=output_dir)

            analyzer_file = Path(result['analyzer_file'])
            content = analyzer_file.read_text()
            assert 'MyCustomLang' in content

    def test_scaffold_analyzer_existing_files_no_force(self):
        """Test scaffolding fails when files exist without force flag."""
        from reveal.cli.scaffold.analyzer import scaffold_analyzer

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create first time
            scaffold_analyzer('test', '.test', output_dir=output_dir)

            # Try to create again without force
            result = scaffold_analyzer('test', '.test', output_dir=output_dir, force=False)

            assert 'error' in result
            assert 'existing_files' in result

    def test_scaffold_analyzer_existing_files_with_force(self):
        """Test scaffolding overwrites files when force=True."""
        from reveal.cli.scaffold.analyzer import scaffold_analyzer

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create first time
            result1 = scaffold_analyzer('test', '.test', output_dir=output_dir)
            analyzer_file = Path(result1['analyzer_file'])

            # Modify file
            original_content = analyzer_file.read_text()
            analyzer_file.write_text("# Modified")

            # Create again with force
            result2 = scaffold_analyzer('test', '.test', output_dir=output_dir, force=True)

            assert 'error' not in result2
            # File should be overwritten
            content = analyzer_file.read_text()
            assert "# Modified" not in content

    def test_scaffold_analyzer_no_output_dir(self):
        """Test scaffolding uses _find_reveal_root when no output_dir."""
        from reveal.cli.scaffold.analyzer import scaffold_analyzer

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'reveal').mkdir(parents=True)
            (root / 'reveal' / '__init__.py').touch()
            (root / 'reveal' / 'analyzers').mkdir(parents=True)

            with patch('reveal.cli.scaffold.analyzer._find_reveal_root', return_value=root):
                result = scaffold_analyzer('test', '.test')

                assert 'error' not in result
                assert 'analyzer_file' in result

    def test_to_class_name(self):
        """Test _to_class_name converts to PascalCase."""
        from reveal.cli.scaffold.analyzer import _to_class_name

        assert _to_class_name('my_module') == 'MyModule'
        assert _to_class_name('my-module') == 'MyModule'
        assert _to_class_name('my module') == 'MyModule'
        assert _to_class_name('MyModule') == 'Mymodule'

    def test_to_module_name(self):
        """Test _to_module_name converts to snake_case."""
        from reveal.cli.scaffold.analyzer import _to_module_name

        assert _to_module_name('MyModule') == 'mymodule'
        assert _to_module_name('my-module') == 'my_module'
        assert _to_module_name('my module') == 'my_module'
        assert _to_module_name('MY_MODULE') == 'my_module'

    def test_find_reveal_root_analyzer(self):
        """Test _find_reveal_root finds reveal root via __init__.py."""
        from reveal.cli.scaffold.analyzer import _find_reveal_root

        # This tests the fallback behavior - returns parent.parent.parent of __file__
        root = _find_reveal_root()
        assert root is not None
        assert isinstance(root, Path)


# ============================================================================
# Test rule.py
# ============================================================================

class TestRuleScaffold:
    """Tests for rule scaffolding."""

    def test_scaffold_rule_basic(self):
        """Test basic rule scaffolding."""
        from reveal.cli.scaffold.rule import scaffold_rule

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = scaffold_rule('C999', 'custom_complexity', category='complexity', output_dir=output_dir)

            assert 'rule_file' in result
            assert 'test_file' in result
            assert 'doc_file' in result
            assert 'next_steps' in result
            assert 'error' not in result

            # Verify files were created
            rule_file = Path(result['rule_file'])
            assert rule_file.exists()
            assert rule_file.name == 'C999.py'

    def test_scaffold_rule_code_normalization(self):
        """Test rule code normalization (uppercase)."""
        from reveal.cli.scaffold.rule import scaffold_rule

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = scaffold_rule('c999', 'test', output_dir=output_dir)

            rule_file = Path(result['rule_file'])
            assert rule_file.name == 'C999.py'

    def test_scaffold_rule_category_normalization(self):
        """Test category normalization (lowercase, underscores)."""
        from reveal.cli.scaffold.rule import scaffold_rule

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = scaffold_rule('C999', 'test', category='My-Category Name', output_dir=output_dir)

            rule_file = Path(result['rule_file'])
            assert 'my_category_name' in str(rule_file)

    def test_scaffold_rule_existing_files_no_force(self):
        """Test scaffolding fails when files exist without force flag."""
        from reveal.cli.scaffold.rule import scaffold_rule

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create first time
            scaffold_rule('C999', 'test', output_dir=output_dir)

            # Try to create again without force
            result = scaffold_rule('C999', 'test', output_dir=output_dir, force=False)

            assert 'error' in result
            assert 'existing_files' in result

    def test_scaffold_rule_existing_files_with_force(self):
        """Test scaffolding overwrites files when force=True."""
        from reveal.cli.scaffold.rule import scaffold_rule

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create first time
            result1 = scaffold_rule('C999', 'test', output_dir=output_dir)
            rule_file = Path(result1['rule_file'])

            # Modify file
            rule_file.write_text("# Modified")

            # Create again with force
            result2 = scaffold_rule('C999', 'test', output_dir=output_dir, force=True)

            assert 'error' not in result2
            content = rule_file.read_text()
            assert "# Modified" not in content

    def test_scaffold_rule_no_output_dir(self):
        """Test scaffolding uses _find_reveal_root when no output_dir."""
        from reveal.cli.scaffold.rule import scaffold_rule

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'reveal').mkdir(parents=True)
            (root / 'reveal' / '__init__.py').touch()

            with patch('reveal.cli.scaffold.rule._find_reveal_root', return_value=root):
                result = scaffold_rule('C999', 'test')

                assert 'error' not in result
                assert 'rule_file' in result

    def test_scaffold_rule_creates_init_file(self):
        """Test scaffolding creates __init__.py in category directory."""
        from reveal.cli.scaffold.rule import scaffold_rule

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = scaffold_rule('C999', 'test', category='newcat', output_dir=output_dir)

            rule_file = Path(result['rule_file'])
            init_file = rule_file.parent / '__init__.py'
            assert init_file.exists()

    def test_scaffold_rule_doesnt_overwrite_init(self):
        """Test scaffolding doesn't overwrite existing __init__.py."""
        from reveal.cli.scaffold.rule import scaffold_rule

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            category_dir = output_dir / 'rules' / 'test'
            category_dir.mkdir(parents=True)

            init_file = category_dir / '__init__.py'
            init_file.write_text("# Custom init content")

            result = scaffold_rule('C999', 'test', category='test', output_dir=output_dir, force=True)

            # __init__.py should still have custom content
            assert init_file.read_text() == "# Custom init content"

    def test_get_rule_prefix_and_severity(self):
        """Test _get_rule_prefix_and_severity mapping."""
        from reveal.cli.scaffold.rule import _get_rule_prefix_and_severity

        # Test known mappings
        assert _get_rule_prefix_and_severity('B001') == ('B', 'HIGH')
        assert _get_rule_prefix_and_severity('E001') == ('E', 'LOW')
        assert _get_rule_prefix_and_severity('F001') == ('F', 'MEDIUM')
        assert _get_rule_prefix_and_severity('C001') == ('C', 'MEDIUM')
        assert _get_rule_prefix_and_severity('S001') == ('S', 'HIGH')
        assert _get_rule_prefix_and_severity('V001') == ('V', 'MEDIUM')
        assert _get_rule_prefix_and_severity('N001') == ('N', 'LOW')

    def test_get_rule_prefix_and_severity_unknown(self):
        """Test _get_rule_prefix_and_severity with unknown prefix."""
        from reveal.cli.scaffold.rule import _get_rule_prefix_and_severity

        prefix, severity = _get_rule_prefix_and_severity('X999')
        assert prefix == 'X'
        assert severity == 'MEDIUM'  # Default

    def test_scaffold_rule_known_prefix_category_value(self):
        """Test rule with known prefix uses RulePrefix enum."""
        from reveal.cli.scaffold.rule import scaffold_rule

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = scaffold_rule('C999', 'test', output_dir=output_dir)

            rule_file = Path(result['rule_file'])
            content = rule_file.read_text()
            assert 'RulePrefix.C' in content

    def test_scaffold_rule_unknown_prefix_category_value(self):
        """Test rule with unknown prefix uses string."""
        from reveal.cli.scaffold.rule import scaffold_rule

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            result = scaffold_rule('X999', 'test', output_dir=output_dir)

            rule_file = Path(result['rule_file'])
            content = rule_file.read_text()
            assert '"X"' in content
            assert 'RulePrefix.X' not in content

    def test_find_reveal_root_rule(self):
        """Test _find_reveal_root finds reveal root via __init__.py."""
        from reveal.cli.scaffold.rule import _find_reveal_root

        # This tests the fallback behavior - returns parent.parent.parent of __file__
        root = _find_reveal_root()
        assert root is not None
        assert isinstance(root, Path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
