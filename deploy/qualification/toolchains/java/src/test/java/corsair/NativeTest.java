package corsair;

import static org.junit.jupiter.api.Assertions.assertEquals;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class NativeTest {
    @TempDir Path directory;

    @Test void nativeRoundtrip() throws Exception {
        byte[] bytes = "native Java fixture\n".getBytes(StandardCharsets.UTF_8);
        Path path = directory.resolve("roundtrip.txt");
        Files.write(path, bytes);
        assertEquals("native Java fixture\n", Files.readString(path));
        assertEquals(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)),
                     HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path))));
    }

    @Test void nativeRuntime() {
        assertEquals(17, Runtime.version().feature());
    }
}
