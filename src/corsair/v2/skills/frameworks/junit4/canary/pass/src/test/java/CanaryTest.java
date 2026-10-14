import static org.junit.Assert.assertTrue;

import java.nio.file.Files;
import java.nio.file.Paths;
import org.junit.Test;

public class CanaryTest {
    @Test
    public void test_canary() throws Exception {
        Files.write(Paths.get(System.getenv("CORSAIR_MARKER_DIR"), "start"), new byte[0]);
        int total = 1 + 1;
        assertTrue(System.getenv("CORSAIR_TOKEN"), total == 2);
        Files.write(Paths.get(System.getenv("CORSAIR_MARKER_DIR"), "end"), new byte[0]);
    }
}
