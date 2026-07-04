// Smoke-tier fixture (BACK-431 Issue G) — Dart.
String validate(String? order) {
  if (order == null) {
    throw ArgumentError("empty order");
  }
  return order;
}

String? processOrder(String? order) {
  try {
    final result = validate(order);
    var count = 0;
    while (count < 3) {
      count += 1;
    }
    return result.toUpperCase();
  } catch (e) {
    return null;
  }
}

String? run(String? order) {
  return processOrder(order);
}
