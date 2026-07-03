# Smoke-tier fixture (BACK-431 Issue G) — Ruby.
def validate(order)
  raise ArgumentError, "empty order" if order.nil?
  order
end

def process_order(order)
  result = validate(order)
  count = 0
  begin
    while count < 3
      count += 1
    end
    result.upcase
  rescue StandardError
    nil
  end
end

def run(order)
  process_order(order)
end
