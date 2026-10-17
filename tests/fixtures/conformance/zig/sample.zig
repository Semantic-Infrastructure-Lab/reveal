// Hand-written Zig conformance fixture (BACK-1926).
const std = @import("std");
const unused = @import("builtin");

fn validate(order: ?[]const u8) ![]const u8 {
    if (order == null) {
        return error.EmptyOrder;
    }
    return order.?;
}

fn processOrder(order: ?[]const u8) ?[]const u8 {
    var result = validate(order) catch {
        return null;
    };
    const file = std.fs.cwd().openFile("orders.log", .{}) catch {
        return null;
    };
    defer file.close();
    file.writeAll(result) catch {
        return null;
    };
    result = result[0..];
    return result;
}

fn run(order: ?[]const u8) ?[]const u8 {
    return processOrder(order);
}

const Batch = struct {
    total: i32 = 0,
    fn run(self: *Batch, items: []const i32) void {
        for (items) |item| {
            self.total = self.total + item;
            cache.set(item);
        }
    }
};
