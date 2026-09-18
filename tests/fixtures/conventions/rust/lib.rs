use serde::Serialize;
use std::collections::HashMap;

fn main() {
    used();
}

fn used() -> HashMap<i32, i32> {
    HashMap::new()
}

fn orphan() {}

#[cfg(test)]
mod tests {
    #[test]
    fn used_returns_map() {
        super::used();
    }
}
