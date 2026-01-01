"""Tests for multi-language import extractors (JavaScript/TypeScript, Go, Rust)."""

import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile
from reveal.analyzers.imports import extract_js_imports, extract_go_imports, extract_rust_imports


class TestJavaScriptImports:
    """Test JavaScript/TypeScript import extraction."""

    def test_es6_named_imports(self):
        """Test ES6 named imports."""
        code = "import { foo, bar } from './module';\n"

        with NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_js_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == './module'
            assert set(imports[0].imported_names) == {'foo', 'bar'}
            assert imports[0].import_type == 'es6_import'
            assert imports[0].is_relative
        finally:
            file_path.unlink()

    def test_es6_default_import(self):
        """Test ES6 default imports."""
        code = "import React from 'react';\n"

        with NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_js_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'react'
            assert imports[0].imported_names == ['React']
            assert imports[0].import_type == 'default_import'
            assert not imports[0].is_relative
        finally:
            file_path.unlink()

    def test_es6_namespace_import(self):
        """Test ES6 namespace imports (import * as)."""
        code = "import * as utils from './utils';\n"

        with NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_js_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == './utils'
            assert imports[0].imported_names == ['*']
            assert imports[0].alias == 'utils'
            assert imports[0].import_type == 'namespace_import'
            assert imports[0].is_relative
        finally:
            file_path.unlink()

    def test_es6_side_effect_import(self):
        """Test ES6 side-effect imports."""
        code = "import './styles.css';\n"

        with NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_js_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == './styles.css'
            assert imports[0].imported_names == []
            assert imports[0].import_type == 'side_effect_import'
            assert imports[0].is_relative
        finally:
            file_path.unlink()

    def test_typescript_type_import(self):
        """Test TypeScript type imports."""
        code = "import type { Foo, Bar } from './types';\n"

        with NamedTemporaryFile(mode='w', suffix='.ts', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_js_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == './types'
            assert set(imports[0].imported_names) == {'Foo', 'Bar'}
            assert imports[0].import_type == 'es6_import'
        finally:
            file_path.unlink()

    def test_commonjs_require(self):
        """Test CommonJS require()."""
        code = "const utils = require('./utils');\n"

        with NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_js_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == './utils'
            assert imports[0].imported_names == ['utils']
            assert imports[0].import_type == 'commonjs_require'
            assert imports[0].is_relative
        finally:
            file_path.unlink()

    def test_commonjs_destructured_require(self):
        """Test CommonJS destructured require()."""
        code = "const { foo, bar } = require('./utils');\n"

        with NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_js_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == './utils'
            assert set(imports[0].imported_names) == {'foo', 'bar'}
            assert imports[0].import_type == 'commonjs_require'
        finally:
            file_path.unlink()

    def test_dynamic_import(self):
        """Test dynamic import()."""
        code = "const module = await import('./module');\n"

        with NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_js_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == './module'
            assert imports[0].import_type == 'dynamic_import'
            assert imports[0].is_relative
        finally:
            file_path.unlink()

    def test_mixed_imports(self):
        """Test file with multiple import types."""
        code = """import React from 'react';
import { useState, useEffect } from 'react';
import * as utils from './utils';
const helper = require('./helper');
"""

        with NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_js_imports(file_path)

            assert len(imports) == 4

            # Check we got all the different types
            types = {imp.import_type for imp in imports}
            assert 'default_import' in types
            assert 'es6_import' in types
            assert 'namespace_import' in types
            assert 'commonjs_require' in types
        finally:
            file_path.unlink()

    def test_multiline_import(self):
        """Test multiline ES6 import."""
        code = """import {
    foo,
    bar,
    baz
} from './module';
"""

        with NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_js_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == './module'
            assert set(imports[0].imported_names) == {'foo', 'bar', 'baz'}
        finally:
            file_path.unlink()

    def test_relative_vs_absolute_paths(self):
        """Test detection of relative vs absolute paths."""
        code = """import local from './local';
import parent from '../parent';
import npm from 'npm-package';
import scoped from '@scope/package';
"""

        with NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_js_imports(file_path)

            assert len(imports) == 4

            # Check relative detection
            relative_modules = {imp.module_name for imp in imports if imp.is_relative}
            absolute_modules = {imp.module_name for imp in imports if not imp.is_relative}

            assert relative_modules == {'./local', '../parent'}
            assert absolute_modules == {'npm-package', '@scope/package'}
        finally:
            file_path.unlink()


class TestGoImports:
    """Test Go import extraction."""

    def test_single_import(self):
        """Test single import statement."""
        code = 'import "fmt"\n'

        with NamedTemporaryFile(mode='w', suffix='.go', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_go_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'fmt'
            assert imports[0].imported_names == ['fmt']
            assert imports[0].import_type == 'go_import'
            assert not imports[0].is_relative
        finally:
            file_path.unlink()

    def test_grouped_imports(self):
        """Test grouped import block."""
        code = """import (
    "fmt"
    "os"
    "strings"
)
"""

        with NamedTemporaryFile(mode='w', suffix='.go', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_go_imports(file_path)

            assert len(imports) == 3
            modules = {imp.module_name for imp in imports}
            assert modules == {'fmt', 'os', 'strings'}

            for imp in imports:
                assert imp.import_type == 'go_import'
        finally:
            file_path.unlink()

    def test_aliased_import(self):
        """Test aliased import."""
        code = 'import f "fmt"\n'

        with NamedTemporaryFile(mode='w', suffix='.go', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_go_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'fmt'
            assert imports[0].alias == 'f'
            assert imports[0].import_type == 'aliased_import'
        finally:
            file_path.unlink()

    def test_dot_import(self):
        """Test dot import (imports into current namespace)."""
        code = 'import . "fmt"\n'

        with NamedTemporaryFile(mode='w', suffix='.go', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_go_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'fmt'
            assert imports[0].alias == '.'
            assert imports[0].import_type == 'dot_import'
        finally:
            file_path.unlink()

    def test_blank_import(self):
        """Test blank import (side-effect only)."""
        code = 'import _ "database/sql/driver"\n'

        with NamedTemporaryFile(mode='w', suffix='.go', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_go_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'database/sql/driver'
            assert imports[0].alias == '_'
            assert imports[0].import_type == 'blank_import'
        finally:
            file_path.unlink()

    def test_external_package(self):
        """Test external package import."""
        code = 'import "github.com/user/repo/pkg"\n'

        with NamedTemporaryFile(mode='w', suffix='.go', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_go_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'github.com/user/repo/pkg'
            assert imports[0].imported_names == ['pkg']
            assert not imports[0].is_relative
        finally:
            file_path.unlink()

    def test_mixed_import_block(self):
        """Test grouped imports with different types."""
        code = """import (
    "fmt"
    f "os"
    . "strings"
    _ "database/sql"
)
"""

        with NamedTemporaryFile(mode='w', suffix='.go', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_go_imports(file_path)

            assert len(imports) == 4

            # Check different types
            types = {imp.import_type for imp in imports}
            assert types == {'go_import', 'aliased_import', 'dot_import', 'blank_import'}
        finally:
            file_path.unlink()


class TestRustImports:
    """Test Rust import (use statement) extraction."""

    def test_simple_use(self):
        """Test simple use statement."""
        code = "use std::collections::HashMap;\n"

        with NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_rust_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'std::collections::HashMap'
            assert imports[0].imported_names == ['HashMap']
            assert imports[0].import_type == 'rust_use'
            assert not imports[0].is_relative
        finally:
            file_path.unlink()

    def test_nested_use(self):
        """Test nested use statement."""
        code = "use std::{fs, io};\n"

        with NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_rust_imports(file_path)

            # Nested imports create separate statements
            assert len(imports) == 2
            modules = {imp.module_name for imp in imports}
            assert modules == {'std::fs', 'std::io'}
        finally:
            file_path.unlink()

    def test_glob_use(self):
        """Test glob use (use path::*)."""
        code = "use std::collections::*;\n"

        with NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_rust_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'std::collections::*'
            assert imports[0].imported_names == ['*']
            assert imports[0].import_type == 'glob_use'
        finally:
            file_path.unlink()

    def test_aliased_use(self):
        """Test aliased use statement."""
        code = "use std::io::Result as IoResult;\n"

        with NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_rust_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'std::io::Result'
            assert imports[0].alias == 'IoResult'
            assert imports[0].import_type == 'aliased_use'
        finally:
            file_path.unlink()

    def test_self_import(self):
        """Test self relative import."""
        code = "use self::module::Item;\n"

        with NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_rust_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'self::module::Item'
            assert imports[0].is_relative
        finally:
            file_path.unlink()

    def test_super_import(self):
        """Test super relative import."""
        code = "use super::module::Item;\n"

        with NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_rust_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'super::module::Item'
            assert imports[0].is_relative
        finally:
            file_path.unlink()

    def test_crate_import(self):
        """Test crate relative import."""
        code = "use crate::module::Item;\n"

        with NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_rust_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'crate::module::Item'
            assert imports[0].is_relative
        finally:
            file_path.unlink()

    def test_pub_use(self):
        """Test pub use statement (visibility modifier stripped)."""
        code = "pub use std::collections::HashMap;\n"

        with NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_rust_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'std::collections::HashMap'
        finally:
            file_path.unlink()

    def test_nested_with_aliases(self):
        """Test nested use with aliases."""
        code = "use std::io::{Read as R, Write as W};\n"

        with NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_rust_imports(file_path)

            # Creates separate statements for each nested item
            assert len(imports) == 2

            # Check aliases
            aliases = {imp.alias for imp in imports if imp.alias}
            assert aliases == {'R', 'W'}
        finally:
            file_path.unlink()

    def test_external_crate(self):
        """Test external crate import."""
        code = "use serde::Serialize;\n"

        with NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
            f.write(code)
            f.flush()
            file_path = Path(f.name)

        try:
            imports = extract_rust_imports(file_path)

            assert len(imports) == 1
            assert imports[0].module_name == 'serde::Serialize'
            assert not imports[0].is_relative
        finally:
            file_path.unlink()
