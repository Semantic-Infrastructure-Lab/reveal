// Conformance fixture (BACK-422 Tier 1/2) — C++
#include <cstdio>
#include <string>
#include <vector>  // unused on purpose -- must still be flagged by imports://

#define CHECK_OR_RETURN(cond, val) if (!(cond)) return (val)

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
    CHECK_OR_RETURN(result < 1000, -1);
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

// BACK-439b/c fixture addition: loop + field write + call effect, added
// standalone (not touching process_order's line-numbered asserts), same
// precedent as Rust's count_down (BACK-427/430).
class Batch {
public:
    int total = 0;
    void run(std::vector<int>& items) {
        for (int item : items) {
            this->total = this->total + item;
            cache.set(item);
        }
    }
};
