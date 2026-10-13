package corsair.sample;

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

class BrokenTest {
    private static String helper(String value) {
        if (value.isEmpty()) {
            throw new IllegalStateException("fixture setup failed");
        }
        return value;
    }

    @Test void setupErrors() {
        System.err.println("about to fail setup");
        assertTrue(helper("").isEmpty());
    }

    @Disabled("not applicable")
    @Test void skippedTest() {
        assertTrue(true);
    }
}
