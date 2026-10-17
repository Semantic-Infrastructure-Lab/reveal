// Hand-written Dart conformance fixture (BACK-1913).
import 'dart:io';
import 'dart:math' as unused_math;

int validate(int order) {
  if (order <= 0) {
    throw ArgumentError('empty order');
  }
  return order;
}

int processOrder(int order) {
  var result = validate(order);
  try {
    final handle = File('orders.log');
    handle.writeAsStringSync(result.toString());
  } catch (e) {
    return -1;
  }
  result = result * 2;
  return result;
}

int run(int order) {
  return processOrder(order);
}

class Batch {
  int total = 0;
  void run(List<int> items) {
    for (final item in items) {
      this.total = this.total + item;
      cache.set(item);
    }
  }
}

@deprecated
class Reporter extends Batch {
  void summarize() {}
}
