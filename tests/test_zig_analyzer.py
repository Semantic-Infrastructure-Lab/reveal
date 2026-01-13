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


if __name__ == '__main__':
    unittest.main()
