// Conformance fixture (BACK-422 Tier 1) — JavaScript
const fs = require('fs');
const path = require('path');
const util = require('util');  // unused on purpose -- must still be flagged by imports://

function validate(order) {
    if (!order) {
        throw new Error('empty order');
    }
    return order;
}

function processOrder(order) {
    let result = validate(order);
    try {
        fs.writeFileSync(path.join('/tmp', 'orders.log'), String(result));
    } catch (err) {
        return null;
    }
    result = result.toUpperCase();
    return result;
}

function run(order) {
    return processOrder(order);
}

// BACK-439b/c fixture addition: loop + field write + call effect, added
// standalone (not touching processOrder's line-numbered asserts), same
// precedent as Rust's count_down (BACK-427/430).
class Batch {
    constructor() {
        this.total = 0;
    }
    run(items) {
        for (const item of items) {
            this.total = this.total + item;
            cache.set(item);
        }
        return this.total;
    }
}

// Deep-conformance addition (BACK-1106): a subclass, added standalone (not
// touching Batch's line-numbered asserts above). Vanilla JS has no
// decorator syntax, so decorators is genuinely not_supported here.
class Reporter extends Batch {
    summarize() {
        return this.total;
    }
}

module.exports = { run, Batch, Reporter };
