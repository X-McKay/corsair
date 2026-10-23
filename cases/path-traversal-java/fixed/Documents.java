import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Documents {
    public static String readDocument(Path root, String name) throws IOException {
        Path allowed = root.toAbsolutePath().normalize();
        Path candidate = allowed.resolve(name).normalize();
        if (!candidate.startsWith(allowed)) throw new SecurityException("outside root");
        return Files.readString(candidate);
    }
}
