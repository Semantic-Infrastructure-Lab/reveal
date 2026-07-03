// Smoke-tier fixture (BACK-431 Issue G) — Swift.
func validate(_ order: String?) throws -> String {
    guard let order = order else {
        throw ValidationError.empty
    }
    return order
}

func processOrder(_ order: String?) -> String? {
    do {
        let result = try validate(order)
        var count = 0
        while count < 3 {
            count += 1
        }
        return result.uppercased()
    } catch {
        return nil
    }
}

func run(_ order: String?) -> String? {
    return processOrder(order)
}
