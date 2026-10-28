import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class Gate {
    public static String read(String baseRoot, String payload) throws IOException {
        Path root = Path.of(baseRoot).toAbsolutePath().normalize();
        Path candidate = root.resolve(payload).normalize();
        if (!candidate.startsWith(root)) {
            return "blocked";
        }
        return Files.readString(candidate);
    }
}
