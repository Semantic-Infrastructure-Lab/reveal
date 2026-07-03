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

module.exports = { run };
