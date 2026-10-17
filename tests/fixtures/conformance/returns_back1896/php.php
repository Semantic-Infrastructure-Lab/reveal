<?php
function polarity($a, $b) {
    if ($a) {
        return 1;
    } elseif ($b) {
        return 2;
    } else {
        return 3;
    }
    return 4;
}
