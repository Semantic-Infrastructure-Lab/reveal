/* Conformance fixture (BACK-422 Tier 1) — C */
#include <stdio.h>
#include <string.h>  /* unused on purpose -- must still be flagged by imports:// */

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
    if (f == NULL) {
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

/* BACK-439b/c fixture addition: loop + field write + call effect, added
   standalone (not touching process_order's line-numbered asserts), same
   precedent as Rust's count_down (BACK-427/430). */
struct Batch {
    int total;
};

void batch_run(struct Batch *b, int *items, int n) {
    for (int i = 0; i < n; i++) {
        b->total = b->total + items[i];
        cache.set(items[i]);
    }
}
