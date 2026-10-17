# Hand-written GDScript conformance fixture (BACK-1921).
extends Node

const Unused = preload("res://unused.gd")

func validate(order):
    if order == null:
        push_error("empty order")
        return null
    return order

func processOrder(order):
    var result = validate(order)
    if result == null:
        return null
    var file = FileAccess.open("user://orders.log", FileAccess.WRITE)
    file.store_string(str(result))
    result = result * 2
    return result

@rpc
func run(order):
    return processOrder(order)

class Batch:
    var total = 0
    var cache = {}
    func run(items):
        for item in items:
            self.total = self.total + item
            cache.set(item, item)

class Reporter extends Batch:
    func summarize():
        pass
