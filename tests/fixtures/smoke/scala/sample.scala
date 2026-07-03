// Smoke-tier fixture (BACK-431 Issue G) — Scala.
object Sample {
  def validate(order: Option[String]): String = order match {
    case None => throw new IllegalArgumentException("empty order")
    case Some(o) => o
  }

  def processOrder(order: Option[String]): Option[String] = {
    try {
      val result = validate(order)
      var count = 0
      while (count < 3) {
        count += 1
      }
      Some(result.toUpperCase)
    } catch {
      case _: Exception => None
    }
  }

  def run(order: Option[String]): Option[String] = {
    processOrder(order)
  }
}
