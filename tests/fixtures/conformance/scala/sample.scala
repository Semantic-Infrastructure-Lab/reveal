// Hand-written Scala conformance fixture (BACK-1919).
import java.io.FileWriter
import scala.collection.mutable.ArrayBuffer

object Sample {
  def validate(order: Int): Int = {
    if (order <= 0) {
      throw new IllegalArgumentException("empty order")
    }
    return order
  }

  def processOrder(order: Int): Int = {
    var result = validate(order)
    try {
      val writer = new FileWriter("orders.log")
      writer.write(result.toString)
      writer.close()
    } catch {
      case _: Exception => return -1
    }
    result = result * 2
    return result
  }

  def run(order: Int): Int = {
    return processOrder(order)
  }
}

class Batch {
  var total: Int = 0
  def run(items: List[Int]): Unit = {
    for (item <- items) {
      this.total = this.total + item
      cache.set(item)
    }
  }
}

@deprecated("fixture", "1")
class Reporter extends Batch {
  def summarize(): Unit = {}
}
