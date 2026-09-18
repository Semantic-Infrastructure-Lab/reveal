use serde::Serialize;
use std::collections::HashMap;

fn main() {
    used();
}

fn used() -> HashMap<i32, i32> {
    HashMap::new()
}

fn orphan() {}

struct Wrapper;

// Trait dispatch reaches `fmt`; the inherent method has no such excuse.
impl std::fmt::Display for Wrapper {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        write!(f, "w")
    }
}

impl Wrapper {
    fn inherent_dead(&self) {}
}

#[cfg(test)]
mod tests {
    #[test]
    fn used_returns_map() {
        super::used();
    }
}
