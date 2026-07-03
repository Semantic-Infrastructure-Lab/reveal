<?php
// Smoke-tier fixture (BACK-431 Issue G) — PHP.
function validate($order) {
    if (empty($order)) {
        throw new InvalidArgumentException("empty order");
    }
    return $order;
}

function processOrder($order) {
    try {
        $result = validate($order);
        $count = 0;
        while ($count < 3) {
            $count++;
        }
        return strtoupper($result);
    } catch (Exception $e) {
        return null;
    }
}

function run($order) {
    return processOrder($order);
}
