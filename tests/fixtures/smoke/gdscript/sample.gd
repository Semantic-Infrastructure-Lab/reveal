# Smoke-tier fixture (BACK-431 Issue G) — GDScript.
func validate(order):
    if order == null:
        push_error("empty order")
        return null
    return order

func processOrder(order):
    var result = validate(order)
    var count = 0
    while count < 3:
        count += 1
    if result == null:
        return null
    return result.to_upper()

func run(order):
    return processOrder(order)
