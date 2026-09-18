import java.util.List;
import org.apache.commons.lang3.StringUtils;

class Lib {
    static void used() {
        List.of();
    }

    static void orphan() {
        StringUtils.isBlank("x");
    }

    public static void main(String[] args) {}

    // Reached through the framework / the overridden type, never by name.
    @GetMapping("/x")
    void route() {}

    @Override
    public String toString() { return ""; }
}
