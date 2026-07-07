"""Tests for ElixirAnalyzer."""

import pytest
from pathlib import Path
from reveal.analyzers.elixir import ElixirAnalyzer


class TestElixirAnalyzerInit:
    """Test analyzer initialization."""

    def test_init(self):
        """Test analyzer can be instantiated."""
        analyzer = ElixirAnalyzer(str(Path(__file__)))
        assert analyzer is not None
        assert analyzer.language == 'elixir'


_SAMPLE = """
defmodule Calculator do
  @moduledoc "Simple calculator module"

  def add(a, b) do
    a + b
  end

  def subtract(a, b) do
    a - b
  end

  defp multiply(a, b) do
    a * b
  end
end

defmodule MathUtils do
  def square(x), do: x * x

  def cube(x) do
    x * x * x
  end
end
"""


class TestElixirAnalyzerStructure:
    """BACK-480: Elixir definitions are macro *call* shapes, so the generic
    node-kind dispatch extracted zero functions/modules — byte/line count only.
    These tests pin the call-based extraction that fixes that."""

    def _structure(self, tmp_path, code=_SAMPLE):
        test_file = tmp_path / "test.ex"
        test_file.write_text(code)
        return ElixirAnalyzer(str(test_file)).get_structure()

    def test_functions_extracted(self, tmp_path):
        structure = self._structure(tmp_path)
        names = {f["name"] for f in structure["functions"]}
        # def, def, defp across two modules; defp is still a function.
        assert names == {"add", "subtract", "multiply", "square", "cube"}

    def test_modules_extracted_as_classes(self, tmp_path):
        structure = self._structure(tmp_path)
        names = {c["name"] for c in structure["classes"]}
        assert names == {"Calculator", "MathUtils"}

    def test_single_line_do_form(self, tmp_path):
        """`def square(x), do: x * x` (no do/end block) must still extract."""
        structure = self._structure(tmp_path)
        square = next(f for f in structure["functions"] if f["name"] == "square")
        assert square["line"] == 19  # the `def square(x), do:` line (sample has a leading \n)
        assert square["line_count"] == 1  # single-line, no do/end block

    def test_zero_arg_guard_and_macro_forms(self, tmp_path):
        code = """
defmodule Edge do
  def ready do
    :ok
  end

  def guarded(x) when x > 0 do
    x
  end

  defmacro trace(expr) do
    quote do: unquote(expr)
  end

  defguard is_even(n) when rem(n, 2) == 0

  defdelegate other(x), to: Mod
end
"""
        structure = self._structure(tmp_path, code)
        names = {f["name"] for f in structure["functions"]}
        assert names == {"ready", "guarded", "trace", "is_even", "other"}

    def test_complexity_counts_branches(self, tmp_path):
        code = """
defmodule S do
  def classify(state, key) do
    case Map.get(state, key) do
      nil -> :none
      v when is_binary(v) -> :string
      _ -> :other
    end
  end
end
"""
        structure = self._structure(tmp_path, code)
        classify = next(f for f in structure["functions"] if f["name"] == "classify")
        # A `case` with multiple arms/guard is more complex than a flat body.
        assert classify["complexity"] >= 2

    def test_contract_fields_present(self, tmp_path):
        structure = self._structure(tmp_path)
        assert structure["contract_version"] == "1.0"
        assert structure["type"] == "elixir_structure"

    def test_nested_modules_and_protocol(self, tmp_path):
        code = """
defmodule Outer do
  defmodule Inner do
    def inner_fn(x), do: x
  end

  defprotocol Greeter do
    def greet(data)
  end
end
"""
        structure = self._structure(tmp_path, code)
        classes = {c["name"] for c in structure["classes"]}
        # defmodule (nested) + defprotocol all surface as classes.
        assert classes == {"Outer", "Inner", "Greeter"}
        assert "inner_fn" in {f["name"] for f in structure["functions"]}

    def test_expression_only_script_has_no_defs(self, tmp_path):
        """A .exs script with no definitions must not crash and yields empty
        function/class lists (not a false structure)."""
        test_file = tmp_path / "script.exs"
        test_file.write_text('IO.puts("hi")\nx = 1 + 2\n')
        structure = ElixirAnalyzer(str(test_file)).get_structure()
        assert structure.get("functions", []) == []
        assert structure.get("classes", []) == []


class TestElixirElementExtraction:
    """`reveal file.ex <name>` must resolve a def/defmodule the outline lists."""

    def _analyzer(self, tmp_path, code=_SAMPLE):
        test_file = tmp_path / "test.ex"
        test_file.write_text(code)
        return ElixirAnalyzer(str(test_file))

    def test_extract_function_element(self, tmp_path):
        el = self._analyzer(tmp_path).extract_element("function", "add")
        assert el is not None
        assert el["name"] == "add"
        assert "a + b" in el["source"]

    def test_extract_module_element(self, tmp_path):
        el = self._analyzer(tmp_path).extract_element("class", "Calculator")
        assert el is not None
        assert el["source"].startswith("defmodule Calculator")

    def test_extract_missing_element_returns_none_or_grep(self, tmp_path):
        # No such def — must not raise (falls back to base grep, which returns None).
        el = self._analyzer(tmp_path).extract_element("function", "nonexistent_fn")
        assert el is None or el.get("name") == "nonexistent_fn"


class TestElixirAnalyzerRegistration:
    """Test analyzer registration."""

    def test_analyzer_registered(self):
        """Test analyzer is registered for .ex files."""
        from reveal.registry import get_analyzer

        test_path = "test.ex"
        analyzer_class = get_analyzer(test_path)

        assert analyzer_class == ElixirAnalyzer
