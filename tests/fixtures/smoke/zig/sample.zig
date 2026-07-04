// Smoke-tier fixture (BACK-431 Issue G) — Zig.
const std = @import("std");

fn validate(order: ?[]const u8) ![]const u8 {
    if (order == null) {
        return error.EmptyOrder;
    }
    return order.?;
}

fn processOrder(order: ?[]const u8) ?[]const u8 {
    const result = validate(order) catch {
        return null;
    };
    var count: u32 = 0;
    while (count < 3) {
        count += 1;
    }
    return result;
}

fn run(order: ?[]const u8) ?[]const u8 {
    return processOrder(order);
}
