// Smoke-tier fixture (BACK-431 Issue G) — Kotlin.
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
