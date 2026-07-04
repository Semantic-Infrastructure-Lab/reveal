// Conformance fixture (BACK-422 Tier 1) — Java
package sample;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;  // unused on purpose -- must still be flagged by imports://

public class OrderProcessor {
    public static int validate(int order) {
        if (order == 0) {
            throw new IllegalArgumentException("empty order");
        }
        return order;
    }

    public static int processOrder(int order) {
        int result = validate(order);
        try {
            Files.write(Paths.get("/tmp/orders.log"), String.valueOf(result).getBytes());
        } catch (IOException e) {
            return -1;
        }
        result = result * 2;
        return result;
    }

    public static int run(int order) {
        return processOrder(order);
    }
}

// BACK-439b/c fixture addition: loop + field write + call effect, added
// standalone (not touching OrderProcessor's line-numbered asserts), same
// precedent as Rust's count_down (BACK-427/430).
class Batch {
    int total;

    void run(java.util.List<Integer> items) {
        for (int item : items) {
            this.total = this.total + item;
            cache.set(item);
        }
    }
}
