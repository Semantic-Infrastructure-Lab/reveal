// Conformance fixture (BACK-422 Tier 1) — Swift
import Foundation

func validate(_ order: String?) throws -> String {
    guard let order = order else {
        throw ValidationError.empty
    }
    return order
}

func processOrder(_ order: String?) -> String? {
    do {
        var result = try validate(order)
        try? result.write(toFile: "/tmp/orders.log", atomically: true, encoding: .utf8)
        var count = 0
        while count < 3 {
            count += 1
        }
        result = result.uppercased()
        return result
    } catch {
        return nil
    }
}

func run(_ order: String?) -> String? {
    return processOrder(order)
}

// BACK-439b/c fixture addition: loop + field write + call effect, same
// precedent as Go/Rust's Batch — added standalone so it doesn't disturb any
// of processOrder's line-numbered assertions above.
class Batch {
    var total: Int = 0

    func run(_ items: [Int]) {
        for item in items {
            self.total = self.total + item
            cache.set(item)
        }
    }
}
