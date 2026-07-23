"""Tests for Zig analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.zig import ZigAnalyzer


class TestZigAnalyzer(unittest.TestCase):
    """Test suite for Zig source file analysis."""

    def test_basic_function(self):
        """Should parse basic Zig function."""
        code = '''
const std = @import("std");

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    try stdout.print("Hello, World!\\n", .{});
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should return valid structure (dict)
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_struct_definition(self):
        """Should parse Zig struct definitions."""
        code = '''
const std = @import("std");

const Point = struct {
    x: f32,
    y: f32,

    pub fn init(x: f32, y: f32) Point {
        return Point{ .x = x, .y = y };
    }

    pub fn distance(self: Point, other: Point) f32 {
        const dx = self.x - other.x;
        const dy = self.y - other.y;
        return @sqrt(dx * dx + dy * dy);
    }
};

const User = struct {
    id: u32,
    name: []const u8,
    email: []const u8,
    age: u8,
};
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_enum_definition(self):
        """Should parse Zig enum definitions."""
        code = '''
const std = @import("std");

const Color = enum {
    red,
    green,
    blue,

    pub fn toString(self: Color) []const u8 {
        return switch (self) {
            .red => "Red",
            .green => "Green",
            .blue => "Blue",
        };
    }
};

const Status = enum(u8) {
    pending = 0,
    active = 1,
    inactive = 2,
    deleted = 3,
};

const Role = enum {
    guest,
    user,
    admin,
    superadmin,

    pub fn hasPermission(self: Role, permission: []const u8) bool {
        return switch (self) {
            .admin, .superadmin => true,
            else => false,
        };
    }
};
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_union_type(self):
        """Should parse Zig union types."""
        code = '''
const std = @import("std");

const Number = union(enum) {
    int: i32,
    float: f64,
    big: i128,

    pub fn asFloat(self: Number) f64 {
        return switch (self) {
            .int => |x| @intToFloat(f64, x),
            .float => |x| x,
            .big => |x| @intToFloat(f64, x),
        };
    }
};

const Result = union(enum) {
    ok: []const u8,
    err: []const u8,

    pub fn isOk(self: Result) bool {
        return switch (self) {
            .ok => true,
            .err => false,
        };
    }
};
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_error_handling(self):
        """Should parse Zig error handling constructs."""
        code = '''
const std = @import("std");

const FileError = error{
    NotFound,
    PermissionDenied,
    InvalidFormat,
};

const ParseError = error{
    InvalidSyntax,
    UnexpectedToken,
    EOF,
};

fn readFile(path: []const u8) FileError![]const u8 {
    if (path.len == 0) return FileError.InvalidFormat;
    // ... read file logic
    return "file contents";
}

fn parseData(data: []const u8) ParseError!i32 {
    if (data.len == 0) return ParseError.EOF;
    return std.fmt.parseInt(i32, data, 10) catch |err| {
        return ParseError.InvalidSyntax;
    };
}

fn processFile(path: []const u8) !void {
    const data = try readFile(path);
    const value = try parseData(data);
    std.debug.print("Value: {}\\n", .{value});
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_generics(self):
        """Should parse Zig generic functions and types."""
        code = '''
const std = @import("std");

fn swap(comptime T: type, a: *T, b: *T) void {
    const temp = a.*;
    a.* = b.*;
    b.* = temp;
}

fn max(comptime T: type, a: T, b: T) T {
    return if (a > b) a else b;
}

fn GenericList(comptime T: type) type {
    return struct {
        items: []T,
        allocator: std.mem.Allocator,

        pub fn init(allocator: std.mem.Allocator) !GenericList(T) {
            return GenericList(T){
                .items = &[_]T{},
                .allocator = allocator,
            };
        }

        pub fn append(self: *GenericList(T), item: T) !void {
            // ... append logic
        }

        pub fn get(self: GenericList(T), index: usize) ?T {
            if (index >= self.items.len) return null;
            return self.items[index];
        }
    };
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_comptime(self):
        """Should parse Zig comptime constructs."""
        code = '''
const std = @import("std");

fn factorial(comptime n: u32) u32 {
    if (n == 0) return 1;
    return n * factorial(n - 1);
}

fn fibonacci(comptime n: u32) u32 {
    if (n <= 1) return n;
    return fibonacci(n - 1) + fibonacci(n - 2);
}

fn generateArray(comptime size: usize, comptime value: i32) [size]i32 {
    var arr: [size]i32 = undefined;
    comptime var i = 0;
    inline while (i < size) : (i += 1) {
        arr[i] = value;
    }
    return arr;
}

pub fn main() void {
    comptime {
        const result = factorial(5);
        std.debug.print("5! = {}\\n", .{result});
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_async_await(self):
        """Should parse Zig async/await constructs."""
        code = '''
const std = @import("std");

fn asyncAdd(a: i32, b: i32) i32 {
    return a + b;
}

fn asyncTask() !void {
    var frame = async asyncAdd(1, 2);
    const result = await frame;
    std.debug.print("Result: {}\\n", .{result});
}

fn worker(id: u32) !void {
    suspend {
        resume @frame();
    }
    std.debug.print("Worker {} done\\n", .{id});
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_tests(self):
        """Should parse Zig test blocks."""
        code = '''
const std = @import("std");
const expect = std.testing.expect;

fn add(a: i32, b: i32) i32 {
    return a + b;
}

test "basic addition" {
    try expect(add(1, 2) == 3);
    try expect(add(-1, 1) == 0);
    try expect(add(0, 0) == 0);
}

test "struct initialization" {
    const Point = struct {
        x: i32,
        y: i32,
    };

    const p = Point{ .x = 10, .y = 20 };
    try expect(p.x == 10);
    try expect(p.y == 20);
}

test "error handling" {
    const result = add(1, 2);
    try expect(result > 0);
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_build_file(self):
        """Should parse Zig build.zig file."""
        code = '''
const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const exe = b.addExecutable(.{
        .name = "myapp",
        .root_source_file = .{ .path = "src/main.zig" },
        .target = target,
        .optimize = optimize,
    });

    b.installArtifact(exe);

    const run_cmd = b.addRunArtifact(exe);
    run_cmd.step.dependOn(b.getInstallStep());

    if (b.args) |args| {
        run_cmd.addArgs(args);
    }

    const run_step = b.step("run", "Run the app");
    run_step.dependOn(&run_cmd.step);

    const unit_tests = b.addTest(.{
        .root_source_file = .{ .path = "src/main.zig" },
        .target = target,
        .optimize = optimize,
    });

    const run_unit_tests = b.addRunArtifact(unit_tests);

    const test_step = b.step("test", "Run unit tests");
    test_step.dependOn(&run_unit_tests.step);
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_memory_management(self):
        """Should parse Zig memory management code."""
        code = '''
const std = @import("std");
const Allocator = std.mem.Allocator;

fn createBuffer(allocator: Allocator, size: usize) ![]u8 {
    const buffer = try allocator.alloc(u8, size);
    return buffer;
}

fn freeBuffer(allocator: Allocator, buffer: []u8) void {
    allocator.free(buffer);
}

const ArrayList = struct {
    items: []i32,
    allocator: Allocator,

    pub fn init(allocator: Allocator) ArrayList {
        return ArrayList{
            .items = &[_]i32{},
            .allocator = allocator,
        };
    }

    pub fn deinit(self: *ArrayList) void {
        self.allocator.free(self.items);
    }

    pub fn append(self: *ArrayList, item: i32) !void {
        const new_items = try self.allocator.realloc(
            self.items,
            self.items.len + 1,
        );
        new_items[new_items.len - 1] = item;
        self.items = new_items;
    }
};
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_comments(self):
        """Should parse Zig files with comments."""
        code = '''
const std = @import("std");

// This is a single-line comment

/// Documentation comment for the add function
/// This function adds two numbers together
pub fn add(a: i32, b: i32) i32 {
    return a + b;
}

/// User struct representing a system user
const User = struct {
    /// Unique identifier
    id: u32,

    /// User's full name
    name: []const u8,

    /// Email address (must be unique)
    email: []const u8,

    // Internal field - password hash
    password_hash: []const u8,
};

// Multi-line comment (C-style not used in Zig)
// Use multiple single-line comments instead
// Like this
pub fn main() !void {
    // Print hello world
    const stdout = std.io.getStdOut().writer();
    try stdout.print("Hello!\\n", .{});
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters in Zig files."""
        code = '''
const std = @import("std");

// UTF-8 string literals 🚀
const greeting = "Hello, 世界! ¿Cómo estás? 👋";
const emoji = "🌍 🌎 🌏";
const multilang = "Привет мир! 你好世界!";

/// User with Unicode name support
const User = struct {
    id: u32,
    /// Name with full Unicode support: 世界 🌍
    name: []const u8,
};

pub fn main() !void {
    const stdout = std.io.getStdOut().writer();
    // Print with emojis and Unicode
    try stdout.print("Greeting: {s} {s}\\n", .{ greeting, emoji });
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)


    def test_signature_format_no_double_name(self):
        """Signature should be '(params)' not 'name(params)' — display renders name+signature."""
        code = '''
pub fn add(a: i32, b: i32) i32 {
    return a + b;
}
pub fn init() void {}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()
            funcs = {f['name']: f for f in structure.get('functions', [])}

            # Signature must start with '(' — not with the function name
            self.assertIn('add', funcs)
            self.assertEqual(funcs['add']['signature'], '(a, b)')

            # No-param function: signature should be empty string (not the name)
            self.assertIn('init', funcs)
            self.assertEqual(funcs['init']['signature'], '')
        finally:
            os.unlink(temp_path)

    def test_extract_element_by_name(self):
        """reveal file.zig funcname should extract the function source."""
        code = '''
pub fn multiply(a: i32, b: i32) i32 {
    return a * b;
}

pub fn divide(a: i32, b: i32) i32 {
    return @divTrunc(a, b);
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)

            result = analyzer.extract_element('function', 'multiply')
            self.assertIsNotNone(result, "extract_element('function', 'multiply') returned None")
            self.assertEqual(result['name'], 'multiply')
            self.assertIn('multiply', result['source'])
            self.assertNotIn('divide', result['source'])

            result2 = analyzer.extract_element('function', 'divide')
            self.assertIsNotNone(result2)
            self.assertEqual(result2['name'], 'divide')

            # Non-existent function
            self.assertIsNone(analyzer.extract_element('function', 'nonexistent'))
        finally:
            os.unlink(temp_path)


    def test_function_has_line_end(self):
        """Function dicts should include line_end for complexity heuristic."""
        code = '''pub fn short() void {}

pub fn longer(a: i32, b: i32) i32 {
    const x = a + b;
    const y = x * 2;
    return y;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ZigAnalyzer(temp_path)
            structure = analyzer.get_structure()
            funcs = {f['name']: f for f in structure.get('functions', [])}

            self.assertIn('line_end', funcs['short'], "function dict must have 'line_end'")
            self.assertIn('line_end', funcs['longer'])
            # line_end >= line (single-line function: end == start)
            self.assertGreaterEqual(funcs['short']['line_end'], funcs['short']['line'])
            self.assertGreater(funcs['longer']['line_end'], funcs['longer']['line'])
        finally:
            os.unlink(temp_path)


def _resolve_zig_func(path, element='run'):
    """Resolve a Zig function's node the same way the CLI does, and a
    get_text helper bound to its content."""
    from reveal.file_handler import _resolve_func_node
    analyzer = ZigAnalyzer(path)
    func_node, _, _ = _resolve_func_node(analyzer, element)
    content_bytes = analyzer.content.encode('utf-8')

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return func_node, get_text


class TestZigCallsFindsSuffixExprCalls(unittest.TestCase):
    """BACK-431 feature-breadth pass (--calls, real-corpus dogfood on
    Ghostty's formatter.zig cellStyle): Zig has no call-expression wrapper
    node — `foo(x)` / `a.b.c(x)` both parse as one `SuffixExpr` node holding
    [IDENTIFIER, then a bare `FnCallArguments` or a run of `FieldOrFnCall`
    children], unlike every other language's dedicated call node. Every
    call in the real function under audit (`cell.hasStyling()`,
    `self.page.styles.get(...)`) was silently invisible to --calls — total
    blindness, the same failure class Dart's --calls fix addressed."""

    def _write(self, code: str) -> str:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            return f.name

    def test_calls_finds_receiver_qualified_chained_call(self):
        from reveal.adapters.ast.nav_calls import range_calls
        from reveal.treesitter import CALL_NODE_TYPES
        path = self._write('''\
fn run(cell: Cell) bool {
    return self.page.styles.get(cell);
}
''')
        try:
            func_node, get_text = _resolve_zig_func(path)
            calls = range_calls(func_node, 1, 999, get_text, CALL_NODE_TYPES)
            callees = [c['callee'] for c in calls]
            self.assertIn('self.page.styles.get', callees)
        finally:
            os.unlink(path)

    def test_calls_finds_bare_call(self):
        from reveal.adapters.ast.nav_calls import range_calls
        from reveal.treesitter import CALL_NODE_TYPES
        path = self._write('''\
fn run(cell: Cell) bool {
    return cell.hasStyling();
}
''')
        try:
            func_node, get_text = _resolve_zig_func(path)
            calls = range_calls(func_node, 1, 999, get_text, CALL_NODE_TYPES)
            callees = [c['callee'] for c in calls]
            self.assertIn('cell.hasStyling', callees)
        finally:
            os.unlink(path)

    def test_calls_finds_builtin_call(self):
        """BACK-753: `@as`/`@import`/etc. parse as BUILTINIDENTIFIER, a
        distinct leaf kind from a regular IDENTIFIER — `@import` alone
        appears in nearly every real Zig file, so this was a high-impact
        gap, not an edge case.
        """
        from reveal.adapters.ast.nav_calls import range_calls
        from reveal.treesitter import CALL_NODE_TYPES
        path = self._write('''\
fn run() void {
    const b = @as(i32, 10);
    _ = b;
}
''')
        try:
            func_node, get_text = _resolve_zig_func(path)
            calls = range_calls(func_node, 1, 999, get_text, CALL_NODE_TYPES)
            callees = [c['callee'] for c in calls]
            self.assertIn('@as', callees)
        finally:
            os.unlink(path)


class TestZigDepsExcludesMemberNamesAndOwnName(unittest.TestCase):
    """BACK-431 feature-breadth pass (--deps, same Ghostty dogfood): three
    stacked bugs, found in order as each was fixed:
    1. `_collect_identifier_names` matched `identifier`/`simple_identifier`/
       etc. but never Zig's actual (all-caps) `IDENTIFIER` node kind — total
       blindness, --deps found *nothing* in a function with 6+ real reads.
    2. Once that was fixed, every member name in a chain
       (`self.page.styles.get(...)`) read as its own bogus undefined
       variable — Zig's `SuffixExpr` packs a chain of any length into one
       node's children rather than nesting, unlike every other language.
    3. The function's own name (`cellStyle`) also leaked through — Zig
       wraps a function in a fieldless `Decl` containing `FnProto`, which
       `_declared_name_node` had no case for.
    """

    def _write(self, code: str) -> str:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.zig', delete=False, encoding='utf-8') as f:
            f.write(code)
            return f.name

    def test_deps_finds_real_params_at_all(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        path = self._write('''\
fn run(cell: Cell) bool {
    return cell.hasStyling();
}
''')
        try:
            func_node, get_text = _resolve_zig_func(path)
            deps = collect_deps(func_node, 1, 999, get_text)
            names = {d['var'] for d in deps}
            self.assertIn('cell', names)
        finally:
            os.unlink(path)

    def test_deps_excludes_chained_member_names(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        path = self._write('''\
fn run(self: Self, cell: Cell) bool {
    return self.page.styles.get(cell);
}
''')
        try:
            func_node, get_text = _resolve_zig_func(path)
            deps = collect_deps(func_node, 1, 999, get_text)
            names = {d['var'] for d in deps}
            self.assertNotIn('page', names)
            self.assertNotIn('styles', names)
            self.assertNotIn('get', names)
            self.assertIn('self', names)
            self.assertIn('cell', names)
        finally:
            os.unlink(path)

    def test_deps_excludes_own_function_name(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        path = self._write('''\
fn cellStyle(cell: Cell) bool {
    return cell.hasStyling();
}
''')
        try:
            func_node, get_text = _resolve_zig_func(path, element='cellStyle')
            deps = collect_deps(func_node, 1, 999, get_text)
            names = {d['var'] for d in deps}
            self.assertNotIn('cellStyle', names)
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()
