// Smoke-tier fixture (BACK-431 Issue G) — TSX.
function validate(order: string | null): string {
  if (order === null) {
    throw new Error("empty order");
  }
  return order;
}

function processOrder(order: string | null): string | null {
  try {
    const result = validate(order);
    let count = 0;
    while (count < 3) {
      count += 1;
    }
    return result.toUpperCase();
  } catch (e) {
    return null;
  }
}

function run(order: string | null) {
  return processOrder(order);
}

export function Widget({ order }: { order: string | null }) {
  return <div>{run(order)}</div>;
}
