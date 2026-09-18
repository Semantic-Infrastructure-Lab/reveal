import java.util.List;
import org.apache.commons.lang3.StringUtils;

class Lib {
    static void used() {
        List.of();
    }

    static void orphan() {
        StringUtils.isBlank("x");
    }
}
