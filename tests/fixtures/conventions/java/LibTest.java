import org.junit.Test;

class LibTest {
    @Test
    void testUsed() {
        Lib.used();
    }

    // JUnit3 style: no annotation, collected by the `test` name prefix.
    public void testLegacy() {
        Lib.used();
    }
}
