<?php
// Conformance fixture (BACK-422 Tier 1) — PHP
require_once 'unused_lib.php'; // unused on purpose -- documented gap, no unused-import detection

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
        file_put_contents("/tmp/orders.log", $result);
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

// BACK-439b/c fixture addition: loop + field write + call effect, same
// precedent as Go/Rust's Batch — added standalone so it doesn't disturb any
// of processOrder's line-numbered assertions above.
class Batch {
    public $total = 0;

    public function run($items) {
        foreach ($items as $item) {
            $this->total = $this->total + $item;
            $cache->set($item);
        }
    }
}
