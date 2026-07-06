// Conformance fixture (BACK-422 Tier 1) — Kotlin
import java.io.File

fun validate(order: String?): String {
    if (order == null) {
        throw IllegalArgumentException("empty order")
    }
    return order
}

fun processOrder(order: String?): String? {
    val result = validate(order)
    var count = 0
    try {
        File("/tmp/orders.log").appendText(result)
        while (count < 3) {
            count += 1
        }
        return result.uppercase()
    } catch (e: Exception) {
        return null
    }
}

fun run(order: String?): String? {
    return processOrder(order)
}

// BACK-439b/c fixture addition: loop + field write + call effect, same
// precedent as Go/Rust's Batch — added standalone so it doesn't disturb any
// of processOrder's line-numbered assertions above.
class Batch {
    var total: Int = 0

    fun run(items: List<Int>) {
        for (item in items) {
            this.total = this.total + item
            cache.set(item)
        }
    }
}
