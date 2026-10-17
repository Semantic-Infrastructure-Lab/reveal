<?php
$state = [];
function mutate($key) {
    global $state, $created;
    $state[$key] = 1;
    $created = 3;
    $GLOBALS['counter'] = 4;
    $local = [];
    $local[$key] = 5;
}
function parameter($state, $key) { $state[$key] = 1; }
function bare($key) { $state[$key] = 1; }
function sibling($obj) {
    $obj->field = 1;
    $_SESSION['id'] = 2;
}
