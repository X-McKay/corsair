import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Documents {
    public static String readDocument(Path root, String name) throws IOException {
        return Files.readString(root.resolve(name));
    }
}
