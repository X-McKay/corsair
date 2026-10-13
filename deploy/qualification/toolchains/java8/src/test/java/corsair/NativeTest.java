package corsair;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.security.MessageDigest;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

public class NativeTest {
    @Rule public TemporaryFolder directory = new TemporaryFolder();

    @Test public void nativeRoundtrip() throws Exception {
        byte[] bytes = "native Java fixture\n".getBytes(StandardCharsets.UTF_8);
        File file = directory.newFile("roundtrip.txt");
        Files.write(file.toPath(), bytes);
        assertEquals("native Java fixture\n", new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8));
        assertArrayEquals(MessageDigest.getInstance("SHA-256").digest(bytes),
                          MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file.toPath())));
    }

    @Test public void nativeRuntime() {
        assertEquals(8, Integer.parseInt(System.getProperty("java.specification.version").replace("1.", "")));
    }
}
