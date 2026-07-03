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
