"""Tests for TypeScript/React analyzer fixes.

Covers:
- TSX grammar: .tsx uses 'tsx' tree-sitter grammar (not 'typescript'), so JSX-heavy
  components parse without error nodes
- BACK-332: interface_declaration, type_alias_declaration, enum_declaration extracted
- BACK-333: module-scope arrow/function-expression declarations extracted
- BACK-334: Jest/Vitest describe/test/it callbacks indexed for calls://
- BACK-335: TypeScript type-annotation-only imports no longer flagged as unused
"""

import pytest
from pathlib import Path

from reveal.analyzers.typescript import TypeScriptAnalyzer, TSXAnalyzer


# ─── Fixtures ────────────────────────────────────────────────────────────────

REACT_COMPONENT = """\
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Chessboard } from 'react-chessboard';

export interface GameProps {
  gameId: string;
  onResign?: () => void;
}

export type MoveResult = {
  from: string;
  to: string;
  promotion?: string;
};

export enum GameStatus {
  Active = 'active',
  Finished = 'finished',
  Abandoned = 'abandoned',
}

export const useGameState = () => {
  const [count, setCount] = useState(0);
  return count;
};

export function Game({ gameId, onResign }: GameProps) {
  const navigate = useNavigate();
  useEffect(() => {
    fetchGame(gameId);
  }, [gameId]);

  return (
    <div className="game">
      <Chessboard position="start" />
      <button onClick={() => navigate('/lobby')}>Back</button>
    </div>
  );
}

const helper = (x: number): number => x * 2;

function plainFunction() {
  return 1;
}
"""

TS_SERVICE = """\
import { IGameStore } from './stores';
import { IScheduler } from './scheduler';
import { GameId } from './types';

export interface CreateGameRequest {
  playerId: string;
}

export type GameRecord = {
  id: GameId;
  status: string;
};

export enum Color { White = 'white', Black = 'black' }

export class GameService {
  constructor(private store: IGameStore, private scheduler: IScheduler) {}

  async createGame(req: CreateGameRequest): Promise<GameRecord> {
    return this.store.create(req);
  }
}

export const buildGame = (id: GameId): GameRecord => ({
  id,
  status: 'active',
});
"""

TS_TESTS = """\
import { GameService } from './GameService';
import { createMockStore } from './testUtils';

describe('GameService', () => {
  let svc: GameService;

  beforeEach(() => {
    const store = createMockStore();
    svc = new GameService(store, null);
  });

  test('creates a game', async () => {
    const result = await svc.createGame({ playerId: 'p1' });
    expect(result.status).toBe('active');
  });

  it('returns existing game', async () => {
    const game = await svc.findGame('g1');
    expect(game).toBeDefined();
  });
});
"""


# ─── TSX grammar: .tsx uses 'tsx' parser ─────────────────────────────────────

class TestTSXGrammar:
    def test_tsx_analyzer_uses_tsx_language(self):
        assert TSXAnalyzer.language == 'tsx'

    def test_ts_analyzer_uses_typescript_language(self):
        assert TypeScriptAnalyzer.language == 'typescript'

    def test_tsx_parses_jsx_component_without_errors(self, tmp_path):
        f = tmp_path / 'Game.tsx'
        f.write_text(REACT_COMPONENT)
        analyzer = TSXAnalyzer(str(f))
        assert analyzer.tree is not None
        root = analyzer.tree.root_node()
        assert not root.has_error()

    def test_tsx_finds_exported_function_component(self, tmp_path):
        f = tmp_path / 'Game.tsx'
        f.write_text(REACT_COMPONENT)
        structure = TSXAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert 'Game' in names

    def test_tsx_finds_plain_function(self, tmp_path):
        f = tmp_path / 'Game.tsx'
        f.write_text(REACT_COMPONENT)
        structure = TSXAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert 'plainFunction' in names


# ─── BACK-332: Interfaces, type aliases, enums ───────────────────────────────

class TestBack332TypeDeclarations:
    def test_interfaces_extracted_from_ts(self, tmp_path):
        f = tmp_path / 'service.ts'
        f.write_text(TS_SERVICE)
        structure = TypeScriptAnalyzer(str(f)).get_structure()
        names = [i['name'] for i in structure.get('interfaces', [])]
        assert 'CreateGameRequest' in names

    def test_type_aliases_extracted_from_ts(self, tmp_path):
        f = tmp_path / 'service.ts'
        f.write_text(TS_SERVICE)
        structure = TypeScriptAnalyzer(str(f)).get_structure()
        names = [t['name'] for t in structure.get('types', [])]
        assert 'GameRecord' in names

    def test_enums_extracted_from_ts(self, tmp_path):
        f = tmp_path / 'service.ts'
        f.write_text(TS_SERVICE)
        structure = TypeScriptAnalyzer(str(f)).get_structure()
        names = [e['name'] for e in structure.get('enums', [])]
        assert 'Color' in names

    def test_interfaces_extracted_from_tsx(self, tmp_path):
        f = tmp_path / 'Game.tsx'
        f.write_text(REACT_COMPONENT)
        structure = TSXAnalyzer(str(f)).get_structure()
        names = [i['name'] for i in structure.get('interfaces', [])]
        assert 'GameProps' in names

    def test_type_aliases_extracted_from_tsx(self, tmp_path):
        f = tmp_path / 'Game.tsx'
        f.write_text(REACT_COMPONENT)
        structure = TSXAnalyzer(str(f)).get_structure()
        names = [t['name'] for t in structure.get('types', [])]
        assert 'MoveResult' in names

    def test_enums_extracted_from_tsx(self, tmp_path):
        f = tmp_path / 'Game.tsx'
        f.write_text(REACT_COMPONENT)
        structure = TSXAnalyzer(str(f)).get_structure()
        names = [e['name'] for e in structure.get('enums', [])]
        assert 'GameStatus' in names

    def test_interface_has_line_numbers(self, tmp_path):
        f = tmp_path / 'service.ts'
        f.write_text(TS_SERVICE)
        structure = TypeScriptAnalyzer(str(f)).get_structure()
        iface = next(i for i in structure['interfaces'] if i['name'] == 'CreateGameRequest')
        assert iface['line'] > 0
        assert iface['line_end'] >= iface['line']
        assert iface['line_count'] >= 1

    def test_types_file_not_empty(self, tmp_path):
        """types.ts returning 'No structure available' was the worst UX (BACK-332)."""
        types_ts = tmp_path / 'types.ts'
        types_ts.write_text(
            "export interface IFoo { id: string; }\n"
            "export type Bar = { name: string };\n"
            "export enum Status { Active, Inactive }\n"
        )
        structure = TypeScriptAnalyzer(str(types_ts)).get_structure()
        assert structure  # must not be empty
        all_names = (
            [i['name'] for i in structure.get('interfaces', [])] +
            [t['name'] for t in structure.get('types', [])] +
            [e['name'] for e in structure.get('enums', [])]
        )
        assert 'IFoo' in all_names
        assert 'Bar' in all_names
        assert 'Status' in all_names


# ─── BACK-333: Arrow function declarations at module scope ───────────────────

class TestBack333ArrowFunctions:
    def test_arrow_function_extracted_from_tsx(self, tmp_path):
        f = tmp_path / 'Game.tsx'
        f.write_text(REACT_COMPONENT)
        structure = TSXAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert 'useGameState' in names

    def test_arrow_function_extracted_from_ts(self, tmp_path):
        f = tmp_path / 'service.ts'
        f.write_text(TS_SERVICE)
        structure = TypeScriptAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert 'buildGame' in names

    def test_non_module_scope_arrow_not_extracted_as_top_level(self, tmp_path):
        src = "function outer() { const inner = () => 1; }\n"
        f = tmp_path / 'a.ts'
        f.write_text(src)
        structure = TypeScriptAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert 'inner' not in names
        assert 'outer' in names

    def test_arrow_function_has_line_number(self, tmp_path):
        src = "export const myHook = () => { return 1; };\n"
        f = tmp_path / 'hook.ts'
        f.write_text(src)
        structure = TypeScriptAnalyzer(str(f)).get_structure()
        fn = next((fn for fn in structure.get('functions', []) if fn['name'] == 'myHook'), None)
        assert fn is not None
        assert fn['line'] == 1


# ─── BACK-334: Jest/Vitest test callback indexing for calls:// ───────────────

class TestBack334TestCallbacks:
    def test_describe_callback_extracted_as_function(self, tmp_path):
        f = tmp_path / 'service.test.ts'
        f.write_text(TS_TESTS)
        structure = TypeScriptAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert any('describe' in n or 'GameService' in n for n in names)

    def test_test_callback_extracted_as_function(self, tmp_path):
        f = tmp_path / 'service.test.ts'
        f.write_text(TS_TESTS)
        structure = TypeScriptAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert any('creates a game' in n or 'test(' in n for n in names)

    def test_test_callback_calls_indexed(self, tmp_path):
        """calls:// needs createGame to appear in the calls of a test function."""
        f = tmp_path / 'service.test.ts'
        f.write_text(TS_TESTS)
        structure = TypeScriptAnalyzer(str(f)).get_structure()
        all_calls = []
        for fn in structure.get('functions', []):
            all_calls.extend(fn.get('calls', []))
        assert any('createGame' in c for c in all_calls)

    def test_beforeeach_callback_extracted(self, tmp_path):
        f = tmp_path / 'service.test.ts'
        f.write_text(TS_TESTS)
        structure = TypeScriptAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert any('beforeEach' in n for n in names)

    def test_class_methods_extracted_from_ts(self, tmp_path):
        """Class methods (method_definition nodes) must be extractable by name."""
        f = tmp_path / 'GameService.ts'
        f.write_text(
            "class GameService {\n"
            "  async createGame(payload) { return {}; }\n"
            "  getGame(id) { return null; }\n"
            "}\n"
        )
        structure = TypeScriptAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert 'createGame' in names
        assert 'getGame' in names

    def test_class_methods_extracted_from_tsx(self, tmp_path):
        """TSX class methods are also extracted."""
        f = tmp_path / 'Component.tsx'
        f.write_text(
            "class MyComponent {\n"
            "  render() { return null; }\n"
            "  handleClick() {}\n"
            "}\n"
        )
        structure = TSXAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert 'render' in names
        assert 'handleClick' in names


# ─── BACK-519: class-field arrow-function methods (`foo = () => {}`) ─────────
# `public_field_definition` (TS/TSX) / `field_definition` (JS) class members
# were entirely absent from FUNCTION_NODE_TYPES, silently dropping every
# class method written as an arrow-function field (a common React
# class-component pattern for binding `this`) from get_structure(),
# calls://, check, hotspots, testability, and element-nav alike, with no
# warning. Found via a real 426KB excalidraw file where this hid 113
# methods class-wide.

class TestBack519ClassFieldArrowFunctions:
    def test_class_field_arrow_function_extracted_from_tsx(self, tmp_path):
        f = tmp_path / 'Component.tsx'
        f.write_text(
            "class MyComponent {\n"
            "  private handleClick = (event: MouseEvent) => {\n"
            "    return event;\n"
            "  };\n"
            "}\n"
        )
        structure = TSXAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert 'handleClick' in names

    def test_class_field_arrow_function_extracted_from_ts(self, tmp_path):
        f = tmp_path / 'Service.ts'
        f.write_text(
            "class Service {\n"
            "  private load = async () => {\n"
            "    return null;\n"
            "  };\n"
            "}\n"
        )
        structure = TypeScriptAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert 'load' in names

    def test_class_field_arrow_function_extracted_from_plain_js(self, tmp_path):
        from reveal.analyzers.javascript import JavaScriptAnalyzer
        f = tmp_path / 'component.js'
        f.write_text(
            "class Component {\n"
            "  handleClick = () => {\n"
            "    return 1;\n"
            "  };\n"
            "}\n"
        )
        structure = JavaScriptAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert 'handleClick' in names

    def test_non_function_class_field_not_extracted_as_function(self, tmp_path):
        f = tmp_path / 'Component.tsx'
        f.write_text(
            "class MyComponent {\n"
            "  count = 0;\n"
            "  render() { return null; }\n"
            "}\n"
        )
        structure = TSXAnalyzer(str(f)).get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        assert 'count' not in names
        assert 'render' in names

    def test_class_field_arrow_method_call_resolves_via_calls_index(self, tmp_path):
        """Regression for the original symptom: calls:// found 0 callers because
        both real call sites lived inside class-field arrow methods reveal
        never walked into."""
        f = tmp_path / 'Component.tsx'
        f.write_text(
            "class MyComponent {\n"
            "  private maybeHandleCrop = () => {\n"
            "    snapResizingElements();\n"
            "  };\n"
            "  private maybeHandleResize = () => {\n"
            "    snapResizingElements();\n"
            "  };\n"
            "}\n"
        )
        structure = TSXAnalyzer(str(f)).get_structure()
        callers = [
            fn['name'] for fn in structure.get('functions', [])
            if 'snapResizingElements' in fn.get('calls', [])
        ]
        assert set(callers) == {'maybeHandleCrop', 'maybeHandleResize'}


# ─── BACK-335: Type-annotation-only imports not flagged as unused ─────────────

class TestBack335TypeAnnotationImports:
    def test_type_annotation_symbols_extracted(self, tmp_path):
        """IGameStore used only in ': IGameStore' annotation — must appear in symbols."""
        from reveal.analyzers.imports.javascript import JavaScriptExtractor
        f = tmp_path / 'service.ts'
        f.write_text(TS_SERVICE)
        extractor = JavaScriptExtractor()
        symbols = extractor.extract_symbols(f)
        assert 'IGameStore' in symbols
        assert 'IScheduler' in symbols

    def test_unused_import_check_no_false_positive(self, tmp_path):
        """--check must not flag interface-type-only imports as unused."""
        from reveal.rules.imports.I001 import I001
        rule = I001()
        f = tmp_path / 'service.ts'
        f.write_text(TS_SERVICE)
        detections = rule.check(str(f), None, f.read_text())
        flagged_names = [d.context for d in detections]
        assert not any('IGameStore' in ctx for ctx in flagged_names)
        assert not any('IScheduler' in ctx for ctx in flagged_names)

    def test_genuinely_unused_import_still_flagged(self, tmp_path):
        """An import that's truly unused (not even in type position) should still fire."""
        from reveal.rules.imports.I001 import I001
        rule = I001()
        src = "import { TrulyUnused } from './foo';\nexport const x = 1;\n"
        f = tmp_path / 'file.ts'
        f.write_text(src)
        detections = rule.check(str(f), None, f.read_text())
        assert any('TrulyUnused' in d.context for d in detections)
