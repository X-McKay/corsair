import static org.junit.Assert.assertTrue;

import java.nio.file.Files;
import java.nio.file.Paths;
import org.junit.Test;

public class CanaryTest {
    @Test
    public void test_canary() throws Exception {
        Files.write(Paths.get(System.getenv("CORSAIR_MARKER_DIR"), "start"), new byte[0]);
        int total = 1 + 1;
        boolean holds = total == 3;
        Files.write(Paths.get(System.getenv("CORSAIR_MARKER_DIR"), "check"), (holds ? "holds" : "violated").getBytes("UTF-8"));
        assertTrue(System.getenv("CORSAIR_TOKEN"), holds);
        Files.write(Paths.get(System.getenv("CORSAIR_MARKER_DIR"), "end"), new byte[0]);
    }
}
