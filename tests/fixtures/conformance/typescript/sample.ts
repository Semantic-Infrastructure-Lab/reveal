// Conformance fixture (BACK-422 Tier 1) — TypeScript
import * as fs from 'fs';
import * as path from 'path';
import * as util from 'util';  // unused on purpose -- must still be flagged by imports://

function validate(order: string): string {
    if (!order) {
        throw new Error('empty order');
    }
    return order;
}

function processOrder(order: string): string | null {
    let result = validate(order);
    try {
        fs.writeFileSync(path.join('/tmp', 'orders.log'), result);
    } catch (err) {
        return null;
    }
    result = result.toUpperCase();
    return result;
}

function run(order: string): string | null {
    return processOrder(order);
}

export { run };
