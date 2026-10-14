import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Paths;
import org.junit.jupiter.api.Test;

public class CanaryTest {
    @Test
    void test_canary() throws Exception {
        Files.write(Paths.get(System.getenv("CORSAIR_MARKER_DIR"), "start"), new byte[0]);
        int total = 1 + 1;
        assertTrue(total == 3, System.getenv("CORSAIR_TOKEN"));
        Files.write(Paths.get(System.getenv("CORSAIR_MARKER_DIR"), "end"), new byte[0]);
    }
}
