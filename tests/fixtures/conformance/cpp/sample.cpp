// Conformance fixture (BACK-422 Tier 1) — C++
#include <cstdio>
#include <string>
#include <vector>  // unused on purpose -- must still be flagged by imports://

int validate(int order) {
    if (order == 0) {
        return -1;
    }
    return order;
}

int process_order(int order) {
    int result = validate(order);
    if (result < 0) {
        return -1;
    }
    FILE *f = fopen("/tmp/orders.log", "a");
    if (f == nullptr) {
        return -1;
    }
    fprintf(f, "%d", result);
    fclose(f);
    result = result * 2;
    return result;
}

int run(int order) {
    return process_order(order);
}
