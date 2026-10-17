const state = {};
let count = 0;
function mutate(key) {
    state[key] = 1;
    count = 3;
    let local = {};
    local[key] = 5;
    { let state = {}; state[key] = 6; }
    state[key] = 7;
}
function parameter(state, key) { state[key] = 1; }
function destructured({state}, key) { state[key] = 1; }
function rebound(key) {
    let state = {};
    state[key] = 1;
}
function nested(key) {
    function shadow(state) { state[key] = 2; }
    state[key] = 3;
}
function sibling() {
    this.field = 1;
    process.env.REVEAL_TEST_STATE = '1';
}
