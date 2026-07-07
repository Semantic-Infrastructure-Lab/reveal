# Conformance fixture (BACK-422 Tier 1) — Ruby
require "json" # unused on purpose -- documented gap, no unused-import detection

def validate(order)
  raise ArgumentError, "empty order" if order.nil?
  order
end

def process_order(order)
  result = validate(order)
  count = 0
  begin
    File.open("/tmp/orders.log", "a") { |f| f.write(result) }
    while count < 3
      count += 1
    end
    return result.upcase
  rescue StandardError
    return nil
  end
end

def run(order)
  process_order(order)
end

# BACK-439b/c fixture addition: loop + field write + call effect, same
# precedent as Go/Rust's Batch — Ruby's Class.method (BACK-451/477) and
# .each do iteration (BACK-477) both now resolve correctly, added standalone
# so it doesn't disturb any of process_order's line-numbered assertions above.
class Batch
  def self.run(items)
    items.each do |item|
      @total = @total + item
      cache.set(item)
    end
  end
end

# Deep-conformance additions (gexode-0707): case/when for --ifmap, compound
# ivar assignment for --statewrites, raise for --exits — appended so the
# line-numbered assertions on validate/process_order/Batch above are undisturbed.
def classify(mode)
  case mode
  when :double then 2
  when :neg then -1
  else 0
  end
end

class Accumulator
  def add(x)
    @sum ||= 0
    @sum += x
  end
end
