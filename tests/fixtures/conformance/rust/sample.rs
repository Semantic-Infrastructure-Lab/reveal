// Conformance fixture (BACK-422 Tier 1) — Rust
use std::fs;
use std::io;
use std::collections::HashMap; // unused on purpose -- must still be flagged by imports://

fn validate(order: i32) -> Result<i32, io::Error> {
    if order == 0 {
        return Err(io::Error::new(io::ErrorKind::InvalidInput, "empty order"));
    }
    Ok(order)
}

fn process_order(order: i32) -> Result<i32, io::Error> {
    let mut result = validate(order)?;
    if let Err(e) = fs::write("/tmp/orders.log", result.to_string()) {
        return Err(e);
    }
    result = result * 2;
    Ok(result)
}

fn run(order: i32) -> Result<i32, io::Error> {
    process_order(order)
}

// BACK-427 (remaining part): Rust's while/for/match are `_expression` nodes,
// not `_statement` — not exercised by process_order above, so kept as a
// separate function rather than reshuffling process_order's line-numbered
// assertions.
fn count_down(mut n: i32) -> i32 {
    while n > 0 {
        n = n - 1;
    }
    for i in 0..3 {
        n = n + i;
    }
    match n {
        0 => n = 1,
        _ => n = 2,
    }
    n
}

// BACK-439b/c fixture addition: loop + field write + call effect, added
// standalone (not touching process_order/count_down's line-numbered
// asserts), same precedent as count_down itself (BACK-427/430).
struct Batch {
    total: i32,
}

impl Batch {
    fn run(&mut self, items: &[i32]) {
        for item in items {
            self.total = self.total + item;
            cache.set(*item);
        }
    }
}
