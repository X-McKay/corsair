import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class Gate {
    public static String read(String baseRoot, String payload) throws IOException {
        return Files.readString(Path.of(baseRoot).resolve(payload));
    }
}
